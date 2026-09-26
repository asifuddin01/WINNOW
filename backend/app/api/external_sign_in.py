"""What Google and ORCID sign-ins share once the provider has said who the person is.

A provider's `start` and `callback` are browser navigations that answer with redirects.
An account with two-factor authentication finishes with a code, posted to the provider's
`two-factor` endpoint.
"""

import secrets
import uuid

from fastapi import Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import enforce_limit
from app.api.session_http import clear_cookie, set_cookie, start_session, user_out
from app.config import Settings
from app.errors import ProblemError
from app.models import User
from app.schemas.auth import ExternalSignedIn
from app.security import rate_limit as limits
from app.security.oidc import OneTimeStore
from app.security.rate_limit import RateLimiter
from app.security.sessions import SessionStore
from app.services import audit
from app.services.audit import Actor
from app.services.errors import InvalidSecondFactorError
from app.services.two_factor import TwoFactorService

FLOW_COOKIE = "__Host-winnow_oauth"
PENDING_COOKIE = "__Host-winnow_pending"
FLOW_SECONDS = 600  # to sign in at the provider and come back
PENDING_SECONDS = 300  # to type the authenticator code afterwards
LABELS = {"google": "Google", "orcid": "ORCID"}


def store(request: Request, name: str) -> OneTimeStore:
    found: OneTimeStore = getattr(request.app.state, name)
    return found


def to_page(path: str, **query: str) -> RedirectResponse:
    """Back to one of our pages, with at most one query parameter (`error`, `step`…)."""
    suffix = "".join(f"?{key}={value}" for key, value in list(query.items())[:1])
    response = RedirectResponse(f"{path}{suffix}", status_code=status.HTTP_303_SEE_OTHER)
    clear_cookie(response, FLOW_COOKIE)
    return response


async def take_flow(request: Request, flows: str, state: str | None) -> dict[str, str] | None:
    """The sign-in this browser started. The state must match its cookie, and works once."""
    bound = request.cookies.get(FLOW_COOKIE)
    if not state or not bound or not secrets.compare_digest(state, bound):
        return None
    return await store(request, flows).take(state)


async def sign_in(
    request: Request,
    db: AsyncSession,
    settings: Settings,
    sessions: SessionStore,
    actor: Actor,
    user: User,
    redirect: str,
    method: str,
) -> RedirectResponse:
    """Start a session for `user`, or ask for their second factor first."""
    if user.disabled_at is not None:
        return to_page("/login", error="account_disabled")
    if user.totp_enabled:
        # The provider proves who you are to it; your Winnow second factor still applies.
        await db.commit()
        pending = await store(request, "pending_sign_ins").create(
            {"user_id": str(user.id), "redirect": redirect, "method": method}
        )
        response = to_page("/login", step=f"{method}-2fa")
        set_cookie(response, PENDING_COOKIE, pending, PENDING_SECONDS, "strict")
        return response

    audit.record(db, "auth.login.success", actor, user_id=user.id, after={"method": method})
    await db.commit()
    response = RedirectResponse(redirect, status_code=status.HTTP_303_SEE_OTHER)
    clear_cookie(response, FLOW_COOKIE)
    await start_session(request, response, user, sessions, settings, actor)
    return response


async def finish_two_factor(
    code: str,
    method: str,
    request: Request,
    response: Response,
    db: AsyncSession,
    settings: Settings,
    sessions: SessionStore,
    limiter: RateLimiter,
    two_factor: TwoFactorService,
    actor: Actor,
) -> ExternalSignedIn:
    """Finish a provider sign-in on an account with two-factor authentication."""
    pendings = store(request, "pending_sign_ins")
    token = request.cookies.get(PENDING_COOKIE)
    pending = await pendings.peek(token) if token else None
    user = await db.get(User, uuid.UUID(pending["user_id"])) if pending else None
    if (
        token is None
        or pending is None
        or pending.get("method") != method
        or user is None
        or user.deleted_at is not None
    ):
        raise ProblemError(
            status.HTTP_401_UNAUTHORIZED,
            f"This {LABELS[method]} sign-in has expired. Start again.",
            code=f"{method}_pending_expired",
        )
    subject = f"{method}|{user.id}"
    await enforce_limit(limiter, limits.LOGIN_PER_ACCOUNT, subject, record=False)
    if not await two_factor.verify(user, code, actor):
        await limiter.hit(limits.LOGIN_PER_ACCOUNT, subject)
        audit.record(
            db,
            "auth.login.failure",
            actor,
            user_id=user.id,
            after={"reason": "wrong_second_factor", "method": method},
        )
        await db.commit()
        raise InvalidSecondFactorError
    await pendings.discard(token)
    audit.record(db, "auth.login.success", actor, user_id=user.id, after={"method": method})
    await db.commit()
    await db.refresh(user)
    csrf_token = await start_session(request, response, user, sessions, settings, actor)
    clear_cookie(response, PENDING_COOKIE, samesite="strict")
    return ExternalSignedIn(
        user=await user_out(db, user), csrf_token=csrf_token, redirect=pending["redirect"]
    )
