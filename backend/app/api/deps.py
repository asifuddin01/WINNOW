"""Request-scoped dependencies: who is calling, their session, services, and protections."""

from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlsplit

import httpx
from fastapi import Depends, Request, status

from app.config import Settings
from app.db import SessionDep
from app.email.mailer import Mailer
from app.errors import ProblemError
from app.models import User
from app.security import csrf
from app.security.passwords import Passwords
from app.security.rate_limit import API_PER_USER, Limit, RateLimiter
from app.security.sessions import SESSION_COOKIE, Session, SessionStore, session_key
from app.services.accounts import AccountService
from app.services.audit import Actor
from app.services.errors import NotAuthenticatedError
from app.services.two_factor import TwoFactorService


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_sessions(request: Request) -> SessionStore:
    store: SessionStore = request.app.state.sessions
    return store


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter


def get_passwords(request: Request) -> Passwords:
    passwords: Passwords = request.app.state.passwords
    return passwords


def get_actor(request: Request) -> Actor:
    return Actor(
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionsDep = Annotated[SessionStore, Depends(get_sessions)]
LimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]
PasswordsDep = Annotated[Passwords, Depends(get_passwords)]
ActorDep = Annotated[Actor, Depends(get_actor)]


def get_accounts(
    request: Request,
    db: SessionDep,
    settings: SettingsDep,
    passwords: PasswordsDep,
    sessions: SessionsDep,
) -> AccountService:
    mailer: Mailer = request.app.state.mailer
    http: httpx.AsyncClient = request.app.state.http
    return AccountService(db, settings, passwords, mailer, http, sessions)


def get_two_factor(db: SessionDep, settings: SettingsDep) -> TwoFactorService:
    return TwoFactorService(db, settings)


AccountsDep = Annotated[AccountService, Depends(get_accounts)]
TwoFactorDep = Annotated[TwoFactorService, Depends(get_two_factor)]


def _wait_phrase(seconds: int) -> str:
    if seconds < 90:
        return f"{seconds} seconds"
    return f"{-(-seconds // 60)} minutes"


async def enforce_limit(
    limiter: RateLimiter, limit: Limit, subject: str, *, record: bool = True
) -> None:
    """Count one hit against `limit` (or only look, with record=False); over it, answer
    429 with Retry-After (guide 12.6)."""
    retry_after = await (limiter.hit if record else limiter.check)(limit, subject)
    if retry_after is not None:
        raise ProblemError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many attempts. Try again in {_wait_phrase(retry_after)}.",
            code="rate_limited",
            headers={"Retry-After": str(retry_after)},
        )


@dataclass(frozen=True, slots=True)
class Authenticated:
    user: User
    session: Session


async def get_authenticated(
    request: Request, db: SessionDep, sessions: SessionsDep, limiter: LimiterDep
) -> Authenticated:
    """The signed-in user, or 401. Also applies the per-user API rate limit."""
    raw = request.cookies.get(SESSION_COOKIE)
    session = await sessions.get(raw) if raw else None
    if session is None:
        raise NotAuthenticatedError
    user = await db.get(User, session.user_id)
    if user is None or user.deleted_at is not None:
        await sessions.delete(session.key, session.user_id)
        raise NotAuthenticatedError
    await enforce_limit(limiter, API_PER_USER, str(user.id))
    return Authenticated(user=user, session=session)


AuthDep = Annotated[Authenticated, Depends(get_authenticated)]


def _origin(url: str) -> str | None:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


async def verify_csrf(request: Request) -> None:
    """Every write must come from our own origin and carry a valid CSRF token (guide 12.1)."""
    if request.method in csrf.SAFE_METHODS:
        return
    settings: Settings = request.app.state.settings
    origin = request.headers.get("origin") or _origin(request.headers.get("referer", ""))
    if origin != settings.public_origin:
        raise ProblemError(
            status.HTTP_403_FORBIDDEN, "This request did not come from Winnow.", code="csrf_origin"
        )
    raw_session = request.cookies.get(SESSION_COOKIE)
    if not csrf.token_is_valid(
        settings.secret_key.get_secret_value().encode(),
        request.cookies.get(csrf.CSRF_COOKIE),
        session_key(raw_session) if raw_session else None,
        request.headers.get(csrf.CSRF_HEADER),
    ):
        raise ProblemError(
            status.HTTP_403_FORBIDDEN,
            "Your security token is missing or out of date. Reload the page and try again.",
            code="csrf_invalid",
        )
