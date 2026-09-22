"""Accounts and sessions: /api/v1/auth (guide 10)."""

from typing import Any

from fastapi import APIRouter, Request, Response, status

from app.api.deps import (
    AccountsDep,
    ActorDep,
    AuthDep,
    LimiterDep,
    PasswordsDep,
    SessionsDep,
    SettingsDep,
    TwoFactorDep,
    enforce_limit,
)
from app.config import Settings
from app.db import SessionDep
from app.errors import ProblemError
from app.models import User
from app.schemas.auth import (
    Accepted,
    AuthOptions,
    ChangePasswordRequest,
    CodeRequest,
    CsrfOut,
    DisableTwoFactorRequest,
    EmailRequest,
    LoginRequest,
    RecoveryCodesOut,
    RegisterRequest,
    ResetPasswordRequest,
    SessionOut,
    SignedIn,
    TokenRequest,
    TwoFactorEnabled,
    TwoFactorSetupOut,
    UserOut,
)
from app.schemas.problem import problem_content
from app.security import csrf
from app.security import rate_limit as limits
from app.security.sessions import SESSION_COOKIE, SessionStore, session_key
from app.services import audit
from app.services.audit import Actor
from app.services.errors import InvalidCredentialsError, InvalidSecondFactorError

router = APIRouter(prefix="/auth", tags=["auth"])

Responses = dict[int | str, dict[str, Any]]
UNAUTHORIZED: Responses = {status.HTTP_401_UNAUTHORIZED: problem_content()}
RATE_LIMITED: Responses = {status.HTTP_429_TOO_MANY_REQUESTS: problem_content()}
CHECK_EMAIL = "If the details are right, an email is on its way. Check your inbox."


# --- Cookies and session rotation ----------------------------------------------------


def _secret(settings: Settings) -> bytes:
    return settings.secret_key.get_secret_value().encode()


def _set_cookie(response: Response, name: str, value: str, max_age: int, samesite: str) -> None:
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


def _csrf_nonce(request: Request, response: Response, sessions: SessionStore) -> str:
    nonce = request.cookies.get(csrf.CSRF_COOKIE) or csrf.new_nonce()
    _set_cookie(
        response, csrf.CSRF_COOKIE, nonce, int(sessions.absolute_lifetime.total_seconds()), "strict"
    )
    return nonce


async def _start_session(
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
    _set_cookie(
        response, SESSION_COOKIE, raw, int(sessions.absolute_lifetime.total_seconds()), "lax"
    )
    return csrf.csrf_token(
        _secret(settings), _csrf_nonce(request, response, sessions), session_key(raw)
    )


def _end_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")


def _user_out(user: User) -> UserOut:
    return UserOut.model_validate(user)


# --- Public ------------------------------------------------------------------------


@router.get("/options")
async def auth_options(accounts: AccountsDep, settings: SettingsDep) -> AuthOptions:
    """What the sign-in pages should offer on this instance."""
    return AuthOptions(
        registration=settings.registration,
        single_user=settings.winnow_single_user,
        needs_setup=await accounts.needs_setup(),
        email_enabled=settings.email_enabled,
    )


@router.get("/csrf")
async def get_csrf_token(
    request: Request, response: Response, settings: SettingsDep, sessions: SessionsDep
) -> CsrfOut:
    """The token to send as X-CSRF-Token on every write. Keep it in memory only."""
    raw = request.cookies.get(SESSION_COOKIE)
    nonce = _csrf_nonce(request, response, sessions)
    return CsrfOut(
        csrf_token=csrf.csrf_token(_secret(settings), nonce, session_key(raw) if raw else None)
    )


@router.post(
    "/register",
    status_code=status.HTTP_202_ACCEPTED,
    responses={403: problem_content(), 422: problem_content(), **RATE_LIMITED},
)
async def register(
    body: RegisterRequest, accounts: AccountsDep, limiter: LimiterDep, actor: ActorDep
) -> Accepted:
    await enforce_limit(limiter, limits.REGISTER_PER_IP, actor.ip or "unknown")
    await accounts.register(name=body.name, email=body.email, password=body.password, actor=actor)
    return Accepted(detail=CHECK_EMAIL)


@router.post(
    "/setup",
    status_code=status.HTTP_201_CREATED,
    responses={403: problem_content(), 422: problem_content(), **RATE_LIMITED},
)
async def setup_single_user(
    body: RegisterRequest,
    request: Request,
    response: Response,
    accounts: AccountsDep,
    sessions: SessionsDep,
    settings: SettingsDep,
    limiter: LimiterDep,
    actor: ActorDep,
) -> SignedIn:
    """Single-user mode's first run: create the administrator and sign them in."""
    if not settings.winnow_single_user:
        raise ProblemError(status.HTTP_404_NOT_FOUND)
    await enforce_limit(limiter, limits.REGISTER_PER_IP, actor.ip or "unknown")
    user = await accounts.create_admin(
        name=body.name, email=body.email, password=body.password, actor=actor, only_if_first=True
    )
    token = await _start_session(request, response, user, sessions, settings, actor)
    return SignedIn(user=_user_out(user), csrf_token=token)


@router.post("/verify-email", responses={400: problem_content(), **RATE_LIMITED})
async def verify_email(
    body: TokenRequest, accounts: AccountsDep, limiter: LimiterDep, actor: ActorDep
) -> UserOut:
    await enforce_limit(limiter, limits.VERIFY_EMAIL_PER_IP, actor.ip or "unknown")
    return _user_out(await accounts.verify_email(body.token, actor))


@router.post("/login", responses={**UNAUTHORIZED, **RATE_LIMITED})
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    accounts: AccountsDep,
    sessions: SessionsDep,
    settings: SettingsDep,
    limiter: LimiterDep,
    actor: ActorDep,
) -> SignedIn:
    """Sign in. With 2FA on, the first try answers 401 `totp_required`; send the same
    request again with `totp` set to an authenticator or recovery code."""
    ip = actor.ip or "unknown"
    buckets = (
        (limits.LOGIN_PER_IP, ip),
        (limits.LOGIN_PER_ACCOUNT, f"{ip}|{body.email.lower()}"),
    )
    for limit, subject in buckets:
        await enforce_limit(limiter, limit, subject, record=False)
    try:
        user = await accounts.authenticate(body.email, body.password, body.totp, actor)
    except (InvalidCredentialsError, InvalidSecondFactorError):
        for limit, subject in buckets:
            await limiter.hit(limit, subject)  # only failures count toward the limits
        raise
    token = await _start_session(request, response, user, sessions, settings, actor)
    return SignedIn(user=_user_out(user), csrf_token=token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request, response: Response, sessions: SessionsDep, db: SessionDep, actor: ActorDep
) -> None:
    """End this browser's session. Safe to call when already signed out."""
    if (raw := request.cookies.get(SESSION_COOKIE)) and (session := await sessions.get(raw)):
        await sessions.delete(session.key, session.user_id)
        audit.record(db, "auth.logout", actor, user_id=session.user_id)
        await db.commit()
    _end_session_cookie(response)


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED, responses=RATE_LIMITED)
async def forgot_password(
    body: EmailRequest, accounts: AccountsDep, limiter: LimiterDep, actor: ActorDep
) -> Accepted:
    await enforce_limit(limiter, limits.PASSWORD_RESET_PER_IP, actor.ip or "unknown")
    await accounts.request_password_reset(body.email, actor)
    return Accepted(detail=CHECK_EMAIL)


@router.post(
    "/password/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={400: problem_content(), 422: problem_content(), **RATE_LIMITED},
)
async def reset_password(
    body: ResetPasswordRequest, accounts: AccountsDep, limiter: LimiterDep, actor: ActorDep
) -> None:
    """Set a new password from an emailed link. Signs out every device."""
    await enforce_limit(limiter, limits.VERIFY_EMAIL_PER_IP, actor.ip or "unknown")
    await accounts.reset_password(body.token, body.password, actor)


# --- Signed in ---------------------------------------------------------------------


@router.get("/me", responses=UNAUTHORIZED)
async def me(auth: AuthDep) -> UserOut:
    return _user_out(auth.user)


@router.post(
    "/verify-email/resend",
    status_code=status.HTTP_202_ACCEPTED,
    responses={**UNAUTHORIZED, **RATE_LIMITED},
)
async def resend_verification(
    auth: AuthDep, accounts: AccountsDep, limiter: LimiterDep
) -> Accepted:
    await enforce_limit(limiter, limits.RESEND_VERIFICATION_PER_USER, str(auth.user.id))
    await accounts.resend_verification(auth.user)
    return Accepted(detail="We sent a new verification link to your email address.")


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT, responses=UNAUTHORIZED)
async def logout_all(
    auth: AuthDep, response: Response, sessions: SessionsDep, db: SessionDep, actor: ActorDep
) -> None:
    """Sign out everywhere, this browser included."""
    count = await sessions.delete_all(auth.user.id)
    audit.record(db, "auth.logout_all", actor, user_id=auth.user.id, after={"sessions": count})
    await db.commit()
    _end_session_cookie(response)


@router.post("/password/change", responses={**UNAUTHORIZED, 422: problem_content()})
async def change_password(
    body: ChangePasswordRequest,
    auth: AuthDep,
    request: Request,
    response: Response,
    accounts: AccountsDep,
    sessions: SessionsDep,
    settings: SettingsDep,
    actor: ActorDep,
) -> CsrfOut:
    """Change the password. Other devices are signed out; this one gets a new session id."""
    await accounts.change_password(
        auth.user, body.current_password, body.new_password, auth.session.key, actor
    )
    return CsrfOut(
        csrf_token=await _start_session(request, response, auth.user, sessions, settings, actor)
    )


@router.get("/sessions", responses=UNAUTHORIZED)
async def list_sessions(auth: AuthDep, sessions: SessionsDep) -> list[SessionOut]:
    return [
        SessionOut(
            id=s.key,
            created_at=s.created_at,
            last_seen_at=s.last_seen_at,
            ip=s.ip,
            user_agent=s.user_agent,
            current=s.key == auth.session.key,
        )
        for s in await sessions.list_for_user(auth.user.id)
    ]


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**UNAUTHORIZED, 404: problem_content()},
)
async def revoke_session(
    session_id: str,
    auth: AuthDep,
    response: Response,
    sessions: SessionsDep,
    db: SessionDep,
    actor: ActorDep,
) -> None:
    """Sign out one device. Only your own sessions can be found here."""
    owned = {s.key for s in await sessions.list_for_user(auth.user.id)}
    if session_id not in owned:
        raise ProblemError(status.HTTP_404_NOT_FOUND, "That session does not exist or has ended.")
    await sessions.delete(session_id, auth.user.id)
    audit.record(db, "auth.session.revoked", actor, user_id=auth.user.id)
    await db.commit()
    if session_id == auth.session.key:
        _end_session_cookie(response)


@router.post("/2fa/setup", responses={**UNAUTHORIZED, 409: problem_content()})
async def two_factor_setup(auth: AuthDep, two_factor: TwoFactorDep) -> TwoFactorSetupOut:
    """A new secret for the authenticator app. Nothing changes until /2fa/enable."""
    setup = await two_factor.begin_setup(auth.user)
    return TwoFactorSetupOut(
        secret=setup.secret, otpauth_uri=setup.otpauth_uri, qr_code=setup.qr_code
    )


@router.post("/2fa/enable", responses={**UNAUTHORIZED, 409: problem_content()})
async def two_factor_enable(
    body: CodeRequest,
    auth: AuthDep,
    request: Request,
    response: Response,
    two_factor: TwoFactorDep,
    accounts: AccountsDep,
    sessions: SessionsDep,
    settings: SettingsDep,
    actor: ActorDep,
) -> TwoFactorEnabled:
    """Confirm with a code from the app. Returns recovery codes, shown only this once."""
    codes = await two_factor.enable(auth.user, body.code, actor)
    await accounts.notify_two_factor_changed(auth.user, enabled=True)
    token = await _start_session(request, response, auth.user, sessions, settings, actor)
    return TwoFactorEnabled(recovery_codes=codes, csrf_token=token)


@router.post(
    "/2fa/disable", responses={**UNAUTHORIZED, 409: problem_content(), 422: problem_content()}
)
async def two_factor_disable(
    body: DisableTwoFactorRequest,
    auth: AuthDep,
    request: Request,
    response: Response,
    two_factor: TwoFactorDep,
    accounts: AccountsDep,
    passwords: PasswordsDep,
    sessions: SessionsDep,
    settings: SettingsDep,
    actor: ActorDep,
) -> CsrfOut:
    await two_factor.disable(auth.user, body.password, body.code, passwords, actor)
    await accounts.notify_two_factor_changed(auth.user, enabled=False)
    return CsrfOut(
        csrf_token=await _start_session(request, response, auth.user, sessions, settings, actor)
    )


@router.post("/2fa/recovery-codes", responses={**UNAUTHORIZED, 409: problem_content()})
async def regenerate_recovery_codes(
    body: CodeRequest, auth: AuthDep, two_factor: TwoFactorDep, actor: ActorDep
) -> RecoveryCodesOut:
    """Replace all recovery codes. The old ones stop working."""
    return RecoveryCodesOut(
        recovery_codes=await two_factor.regenerate_recovery_codes(auth.user, body.code, actor)
    )
