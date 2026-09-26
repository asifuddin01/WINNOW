"""Sign in with ORCID: /api/v1/auth/orcid (OpenID Connect; see app.security.orcid).

An iD signs in only to the account it is linked to. Linking starts on the account page
(`link`, an API call that answers with ORCID's address) and comes back through the same
`callback` as a sign-in. `start` and `callback` are browser navigations, as for Google.
"""

import secrets
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import (
    ActorDep,
    AuthDep,
    LimiterDep,
    SessionsDep,
    SettingsDep,
    TwoFactorDep,
    enforce_limit,
)
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
from app.models import User
from app.schemas.auth import CodeRequest, ExternalSignedIn, OrcidLinkStart
from app.schemas.problem import problem_content
from app.security import rate_limit as limits
from app.security.oidc import SignInError
from app.security.orcid import PROVIDER, OrcidClient, authorization_url
from app.security.sessions import SESSION_COOKIE
from app.services.identities import OrcidTakenError, link_orcid, unlink_orcid, user_for_orcid

router = APIRouter(prefix="/auth/orcid", tags=["auth"])

Responses = dict[int | str, dict[str, Any]]
NOT_OFFERED: Responses = {status.HTTP_404_NOT_FOUND: problem_content()}


def _client(request: Request, settings: Settings) -> OrcidClient:
    client: OrcidClient | None = request.app.state.orcid
    if not settings.orcid_enabled or client is None:
        raise ProblemError(status.HTTP_404_NOT_FOUND)
    return client


def _callback_url(settings: Settings) -> str:
    return f"{settings.public_origin}/api/v1/auth/orcid/callback"


async def _begin(
    request: Request,
    response: Response,
    settings: Settings,
    limiter: LimiterDep,
    actor: ActorDep,
    redirect: str,
    link: str,
) -> str:
    """Remember the sign-in this browser starts, and ORCID's address to send it to."""
    _client(request, settings)
    await enforce_limit(limiter, limits.ORCID_PER_IP, actor.ip or "unknown")
    nonce = secrets.token_urlsafe(24)
    state = await store(request, "orcid_flows").create(
        {"nonce": nonce, "redirect": redirect, "link": link}
    )
    # Lax, not Strict: the browser must send it on the navigation back from ORCID.
    set_cookie(response, FLOW_COOKIE, state, FLOW_SECONDS, "lax")
    return authorization_url(
        settings.orcid_base_url,
        settings.orcid_client_id or "",
        _callback_url(settings),
        state,
        nonce,
    )


@router.get("/start", include_in_schema=False)
async def orcid_start(
    request: Request,
    settings: SettingsDep,
    limiter: LimiterDep,
    actor: ActorDep,
    redirect: Annotated[str | None, Query(max_length=2000)] = None,
) -> RedirectResponse:
    """Send the browser to ORCID's sign-in."""
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    response.headers["location"] = await _begin(
        request, response, settings, limiter, actor, safe_redirect(redirect), link=""
    )
    return response


@router.post(
    "/link", responses={**NOT_OFFERED, status.HTTP_429_TOO_MANY_REQUESTS: problem_content()}
)
async def orcid_link(
    request: Request,
    response: Response,
    auth: AuthDep,
    settings: SettingsDep,
    limiter: LimiterDep,
    actor: ActorDep,
) -> OrcidLinkStart:
    """Start linking an ORCID iD to the signed-in account: send the browser to `url`."""
    url = await _begin(
        request, response, settings, limiter, actor, "/account", link=str(auth.user.id)
    )
    return OrcidLinkStart(url=url)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def orcid_unlink(auth: AuthDep, db: SessionDep, actor: ActorDep) -> None:
    """Unlink the account's ORCID iD. Works even after the instance stops offering ORCID."""
    await unlink_orcid(db, auth.user, actor)
    await db.commit()


@router.get("/callback", include_in_schema=False)
async def orcid_callback(
    request: Request,
    db: SessionDep,
    settings: SettingsDep,
    sessions: SessionsDep,
    actor: ActorDep,
    state: Annotated[str | None, Query(max_length=200)] = None,
    code: Annotated[str | None, Query(max_length=2000)] = None,
    error: Annotated[str | None, Query(max_length=200)] = None,
) -> RedirectResponse:
    """ORCID sends the browser back here, from a sign-in or a link."""
    client = _client(request, settings)
    flow = await take_flow(request, "orcid_flows", state)
    if flow is None:
        return to_page("/login", error="orcid_state")

    def fail(reason: str) -> RedirectResponse:
        return (
            to_page("/account", orcid=reason) if flow["link"] else to_page("/login", error=reason)
        )

    if error:
        return fail("orcid_cancelled")
    if not code:
        return fail("orcid_failed")
    try:
        orcid = await client.verify(
            await client.exchange(code, _callback_url(settings)), flow["nonce"]
        )
    except SignInError as exc:
        return fail(exc.code)

    if not flow["link"]:
        found = await user_for_orcid(db, orcid)
        if found is None:
            return to_page("/login", error="orcid_not_linked")
        return await sign_in(
            request, db, settings, sessions, actor, found, flow["redirect"], PROVIDER
        )

    # A link finishes only in the session that started it: on a shared computer, someone
    # who signed in meanwhile must not end up with their iD on the first person's account.
    raw = request.cookies.get(SESSION_COOKIE)
    session = await sessions.get(raw) if raw else None
    user = await db.get(User, uuid.UUID(flow["link"]))
    if session is None or user is None or session.user_id != user.id:
        return to_page("/login", error="orcid_state")
    try:
        await link_orcid(db, user, orcid, actor)
    except OrcidTakenError:
        return fail("orcid_taken")
    await db.commit()
    return to_page("/account", orcid="linked")


EXPIRED: Responses = {status.HTTP_401_UNAUTHORIZED: problem_content()}


@router.post(
    "/two-factor", responses={**EXPIRED, status.HTTP_429_TOO_MANY_REQUESTS: problem_content()}
)
async def orcid_two_factor(
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
    """Finish an ORCID sign-in on an account with two-factor authentication."""
    _client(request, settings)
    return await finish_two_factor(
        body.code, PROVIDER, request, response, db, settings, sessions, limiter, two_factor, actor
    )
