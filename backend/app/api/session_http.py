"""Cookies, session rotation and the user shape, shared by every way of signing in."""

import re

from fastapi import Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import User
from app.schemas.auth import UserOut
from app.security import csrf
from app.security.sessions import SESSION_COOKIE, SessionStore, session_key
from app.services.audit import Actor
from app.services.google_accounts import google_linked

# Pages a sign-in must never send you back to (they would loop or leak a token).
_NOT_A_DESTINATION = re.compile(r"^/(api|login|register|setup|forgot|reset|verify)\b")


def secret_bytes(settings: Settings) -> bytes:
    return settings.secret_key.get_secret_value().encode()


def set_cookie(response: Response, name: str, value: str, max_age: int, samesite: str) -> None:
    # __Host- cookies: Secure, Path=/, no Domain, so no other host can set or read them.
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path="/",
        secure=True,
        httponly=True,
        samesite=samesite,  # type: ignore[arg-type]
    )


def clear_cookie(response: Response, name: str, samesite: str = "lax") -> None:
    response.delete_cookie(name, path="/", secure=True, httponly=True, samesite=samesite)  # type: ignore[arg-type]


def csrf_nonce(request: Request, response: Response, sessions: SessionStore) -> str:
    nonce = request.cookies.get(csrf.CSRF_COOKIE) or csrf.new_nonce()
    set_cookie(
        response, csrf.CSRF_COOKIE, nonce, int(sessions.absolute_lifetime.total_seconds()), "strict"
    )
    return nonce


async def start_session(
    request: Request,
    response: Response,
    user: User,
    sessions: SessionStore,
    settings: Settings,
    actor: Actor,
) -> str:
    """Replace any session the browser had with a new id (guide 12.1: rotate on sign-in and
    privilege change) and return the CSRF token that belongs to it."""
    old = request.cookies.get(SESSION_COOKIE)
    if old and (existing := await sessions.get(old)) is not None:
        await sessions.delete(existing.key, existing.user_id)
    raw = await sessions.create(user.id, actor.ip, actor.user_agent)
    set_cookie(
        response, SESSION_COOKIE, raw, int(sessions.absolute_lifetime.total_seconds()), "lax"
    )
    return csrf.csrf_token(
        secret_bytes(settings), csrf_nonce(request, response, sessions), session_key(raw)
    )


def end_session_cookie(response: Response) -> None:
    clear_cookie(response, SESSION_COOKIE)


async def user_out(db: AsyncSession, user: User) -> UserOut:
    return UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        email_verified=user.email_verified,
        totp_enabled=user.totp_enabled,
        recovery_codes_left=user.recovery_codes_left,
        is_instance_admin=user.is_instance_admin,
        has_password=user.has_password,
        google_linked=await google_linked(db, user),
        created_at=user.created_at,
    )


def safe_redirect(target: str | None) -> str:
    """Only same-site app paths; anything else goes home (no open redirects)."""
    if (
        not target
        or not target.startswith("/")
        or target.startswith(("//", "/\\"))
        or _NOT_A_DESTINATION.match(target)
    ):
        return "/"
    return target
