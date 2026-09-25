"""Sign in with Google: /api/v1/auth/google (OpenID Connect; see app.security.google).

`start` and `callback` are browser navigations, not API calls: they answer with redirects
and stay out of the OpenAPI document. A 2FA account finishes with a code at `two-factor`.
"""

import secrets
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import ActorDep, LimiterDep, SessionsDep, SettingsDep, TwoFactorDep, enforce_limit
from app.api.session_http import clear_cookie, safe_redirect, set_cookie, start_session, user_out
from app.config import Settings
from app.db import SessionDep
from app.errors import ProblemError
from app.models import User
from app.schemas.auth import CodeRequest, GoogleSignedIn
from app.schemas.problem import problem_content
from app.security import rate_limit as limits
from app.security.google import (
    GoogleClient,
    GoogleSignInError,
    OneTimeStore,
    authorization_url,
    pkce_pair,
)
from app.services import audit
from app.services.errors import InvalidSecondFactorError, RegistrationClosedError
from app.services.google_accounts import user_for_google

router = APIRouter(prefix="/auth/google", tags=["auth"])

FLOW_COOKIE = "__Host-winnow_oauth"
PENDING_COOKIE = "__Host-winnow_pending"
FLOW_SECONDS = 600  # to pick an account at Google and come back
PENDING_SECONDS = 300  # to type the authenticator code afterwards


def _client(request: Request, settings: Settings) -> GoogleClient:
    client: GoogleClient | None = request.app.state.google
    if not settings.google_enabled or client is None:
        raise ProblemError(status.HTTP_404_NOT_FOUND)
    return client


def _store(request: Request, name: str) -> OneTimeStore:
    store: OneTimeStore = getattr(request.app.state, name)
    return store


def _callback_url(settings: Settings) -> str:
    return f"{settings.public_origin}/api/v1/auth/google/callback"


def _to_sign_in(error: str | None = None, step: str | None = None) -> RedirectResponse:
    query = f"?error={error}" if error else f"?step={step}" if step else ""
    response = RedirectResponse(f"/login{query}", status_code=status.HTTP_303_SEE_OTHER)
    clear_cookie(response, FLOW_COOKIE)
    return response


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
    state = await _store(request, "google_flows").create(
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
    bound = request.cookies.get(FLOW_COOKIE)
    # The state must match this browser's cookie, and it works once.
    if not state or not bound or not secrets.compare_digest(state, bound):
        return _to_sign_in("google_state")
    flow = await _store(request, "google_flows").take(state)
    if flow is None:
        return _to_sign_in("google_state")
    if error:
        return _to_sign_in("google_cancelled")
    if not code:
        return _to_sign_in("google_failed")
    try:
        id_token = await client.exchange(code, flow["verifier"], _callback_url(settings))
        profile = await client.verify(id_token, flow["nonce"])
        user = await user_for_google(db, settings, profile, actor)
    except GoogleSignInError as exc:
        return _to_sign_in(exc.code)
    except RegistrationClosedError:
        return _to_sign_in("registration_closed")
    if user.disabled_at is not None:
        return _to_sign_in("account_disabled")

    if user.totp_enabled:
        # Google proves who you are to Google; your Winnow second factor still applies.
        await db.commit()
        pending = await _store(request, "google_pending").create(
            {"user_id": str(user.id), "redirect": flow["redirect"]}
        )
        response = _to_sign_in(step="google-2fa")
        set_cookie(response, PENDING_COOKIE, pending, PENDING_SECONDS, "strict")
        return response

    audit.record(db, "auth.login.success", actor, user_id=user.id, after={"method": "google"})
    await db.commit()
    response = RedirectResponse(flow["redirect"], status_code=status.HTTP_303_SEE_OTHER)
    clear_cookie(response, FLOW_COOKIE)
    await start_session(request, response, user, sessions, settings, actor)
    return response


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
) -> GoogleSignedIn:
    """Finish a Google sign-in on an account with two-factor authentication."""
    _client(request, settings)
    pendings = _store(request, "google_pending")
    token = request.cookies.get(PENDING_COOKIE)
    pending = await pendings.peek(token) if token else None
    user = await db.get(User, uuid.UUID(pending["user_id"])) if pending else None
    if token is None or pending is None or user is None or user.deleted_at is not None:
        raise ProblemError(
            status.HTTP_401_UNAUTHORIZED,
            "This Google sign-in has expired. Start again.",
            code="google_pending_expired",
        )
    subject = f"google|{user.id}"
    await enforce_limit(limiter, limits.LOGIN_PER_ACCOUNT, subject, record=False)
    if not await two_factor.verify(user, body.code, actor):
        await limiter.hit(limits.LOGIN_PER_ACCOUNT, subject)
        audit.record(
            db,
            "auth.login.failure",
            actor,
            user_id=user.id,
            after={"reason": "wrong_second_factor", "method": "google"},
        )
        await db.commit()
        raise InvalidSecondFactorError
    await pendings.discard(token)
    audit.record(db, "auth.login.success", actor, user_id=user.id, after={"method": "google"})
    await db.commit()
    await db.refresh(user)
    csrf_token = await start_session(request, response, user, sessions, settings, actor)
    clear_cookie(response, PENDING_COOKIE, samesite="strict")
    return GoogleSignedIn(
        user=await user_out(db, user), csrf_token=csrf_token, redirect=pending["redirect"]
    )
