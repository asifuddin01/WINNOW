"""Sign in with Google: /api/v1/auth/google (OpenID Connect; see app.security.google).

`start` and `callback` are browser navigations, not API calls: they answer with redirects
and stay out of the OpenAPI document. A 2FA account finishes with a code at `two-factor`.
"""

import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import ActorDep, LimiterDep, SessionsDep, SettingsDep, TwoFactorDep, enforce_limit
from app.api.external_sign_in import (
    FLOW_COOKIE,
    FLOW_SECONDS,
    finish_two_factor,
    sign_in,
    store,
    take_flow,
    to_page,
)
from app.api.session_http import safe_redirect, set_cookie
from app.config import Settings
from app.db import SessionDep
from app.errors import ProblemError
from app.schemas.auth import CodeRequest, ExternalSignedIn
from app.schemas.problem import problem_content
from app.security import rate_limit as limits
from app.security.google import PROVIDER, GoogleClient, authorization_url
from app.security.oidc import SignInError, pkce_pair
from app.services.errors import RegistrationClosedError
from app.services.google_accounts import user_for_google

router = APIRouter(prefix="/auth/google", tags=["auth"])


def _client(request: Request, settings: Settings) -> GoogleClient:
    client: GoogleClient | None = request.app.state.google
    if not settings.google_enabled or client is None:
        raise ProblemError(status.HTTP_404_NOT_FOUND)
    return client


def _callback_url(settings: Settings) -> str:
    return f"{settings.public_origin}/api/v1/auth/google/callback"


@router.get("/start", include_in_schema=False)
async def google_start(
    request: Request,
    settings: SettingsDep,
    limiter: LimiterDep,
    actor: ActorDep,
    redirect: Annotated[str | None, Query(max_length=2000)] = None,
) -> RedirectResponse:
    """Send the browser to Google's account chooser."""
    _client(request, settings)
    await enforce_limit(limiter, limits.GOOGLE_PER_IP, actor.ip or "unknown")
    verifier, challenge = pkce_pair()
    nonce = secrets.token_urlsafe(24)
    state = await store(request, "google_flows").create(
        {"verifier": verifier, "nonce": nonce, "redirect": safe_redirect(redirect)}
    )
    response = RedirectResponse(
        authorization_url(
            settings.google_client_id or "", _callback_url(settings), state, nonce, challenge
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )
    # Lax, not Strict: the browser must send it on the navigation back from Google.
    set_cookie(response, FLOW_COOKIE, state, FLOW_SECONDS, "lax")
    return response


@router.get("/callback", include_in_schema=False)
async def google_callback(
    request: Request,
    db: SessionDep,
    settings: SettingsDep,
    sessions: SessionsDep,
    actor: ActorDep,
    state: Annotated[str | None, Query(max_length=200)] = None,
    code: Annotated[str | None, Query(max_length=2000)] = None,
    error: Annotated[str | None, Query(max_length=200)] = None,
) -> RedirectResponse:
    """Google sends the browser back here. Every failure lands on the sign-in page."""
    client = _client(request, settings)
    flow = await take_flow(request, "google_flows", state)
    if flow is None:
        return to_page("/login", error="google_state")
    if error:
        return to_page("/login", error="google_cancelled")
    if not code:
        return to_page("/login", error="google_failed")
    try:
        id_token = await client.exchange(
            code, _callback_url(settings), code_verifier=flow["verifier"]
        )
        profile = await client.verify(id_token, flow["nonce"])
        user = await user_for_google(db, settings, profile, actor)
    except SignInError as exc:
        return to_page("/login", error=exc.code)
    except RegistrationClosedError:
        return to_page("/login", error="registration_closed")
    return await sign_in(request, db, settings, sessions, actor, user, flow["redirect"], PROVIDER)


EXPIRED: dict[int | str, dict[str, Any]] = {status.HTTP_401_UNAUTHORIZED: problem_content()}


@router.post(
    "/two-factor", responses={**EXPIRED, status.HTTP_429_TOO_MANY_REQUESTS: problem_content()}
)
async def google_two_factor(
    body: CodeRequest,
    request: Request,
    response: Response,
    db: SessionDep,
    settings: SettingsDep,
    sessions: SessionsDep,
    limiter: LimiterDep,
    two_factor: TwoFactorDep,
    actor: ActorDep,
) -> ExternalSignedIn:
    """Finish a Google sign-in on an account with two-factor authentication."""
    _client(request, settings)
    return await finish_two_factor(
        body.code, PROVIDER, request, response, db, settings, sessions, limiter, two_factor, actor
    )
