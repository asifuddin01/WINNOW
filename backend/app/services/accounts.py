"""Accounts: registration, email verification, sign-in with lockout and 2FA, password changes.

Nothing here reveals whether an email has an account: registration, sign-in and password
reset answer the same way, in about the same time, either way (guide 12.1).
"""

from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.email import messages
from app.email.mailer import Mailer
from app.models import EmailToken, EmailTokenPurpose, User
from app.security.breach import is_breached
from app.security.passwords import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, Passwords
from app.security.sessions import SessionStore
from app.security.tokens import hash_token, new_token
from app.services import audit
from app.services.audit import Actor
from app.services.errors import (
    AccountDisabledError,
    InvalidCredentialsError,
    InvalidSecondFactorError,
    InvalidTokenError,
    RegistrationClosedError,
    SecondFactorRequiredError,
    WeakPasswordError,
)
from app.services.instance import registration_mode
from app.services.members import invite_allows_registration
from app.services.two_factor import IncorrectPasswordError, TwoFactorService

VERIFY_TOKEN_TTL = timedelta(hours=24)
RESET_TOKEN_TTL = timedelta(minutes=30)
MAX_FAILED_SIGN_INS = 10
LOCKOUT = timedelta(minutes=15)


def _now() -> datetime:
    return datetime.now(UTC)


class AccountService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        passwords: Passwords,
        mailer: Mailer,
        http: httpx.AsyncClient,
        sessions: SessionStore,
    ) -> None:
        self._db = db
        self._settings = settings
        self._passwords = passwords
        self._mailer = mailer
        self._http = http
        self._sessions = sessions
        self._two_factor = TwoFactorService(db, settings)

    # --- Registration and verification ---------------------------------------------

    async def needs_setup(self) -> bool:
        """Single-user mode before its administrator exists."""
        return self._settings.winnow_single_user and not await self._any_user()

    async def register(
        self, *, name: str, email: str, password: str, actor: Actor, invite_token: str | None = None
    ) -> None:
        """Create an unverified account and email a verification link. An address that
        already has an account gets a heads-up email instead; the caller cannot tell which
        happened."""
        if self._settings.winnow_single_user:
            raise RegistrationClosedError("This Winnow instance is set up for a single user.")
        mode = await registration_mode(self._db, self._settings)
        if mode == "invite_only" and not await invite_allows_registration(
            self._db, invite_token, email
        ):
            raise RegistrationClosedError("Registration on this Winnow instance is by invitation.")
        if mode == "closed":
            raise RegistrationClosedError
        await self.check_password(password, email=email)
        # Hash either way, so an existing address does not answer faster.
        password_hash = await self._passwords.hash(password)
        existing = await self._user_by_email(email)
        if existing is not None:
            await self._notify_existing_account(existing, actor)
            return
        user = User(name=name, email=email, password_hash=password_hash)
        self._db.add(user)
        try:
            await self._db.flush()
        except IntegrityError:  # registered by a concurrent request a moment ago
            await self._db.rollback()
            if (existing := await self._user_by_email(email)) is not None:
                await self._notify_existing_account(existing, actor)
            return
        token = await self._issue_token(user, EmailTokenPurpose.VERIFY, VERIFY_TOKEN_TTL)
        audit.record(
            self._db, "auth.register", actor, user_id=user.id, entity_type="user", entity_id=user.id
        )
        await self._db.commit()
        await self._mailer.send(
            messages.verify_email(user.email, user.name, self._link("verify", token))
        )

    async def verify_email(self, token: str, actor: Actor) -> User:
        email_token = await self._claim_token(token, EmailTokenPurpose.VERIFY)
        user = await self._db.get_one(User, email_token.user_id)
        if user.email_verified_at is None:
            user.email_verified_at = _now()
            audit.record(self._db, "auth.email_verified", actor, user_id=user.id)
        await self._db.commit()
        return user

    async def resend_verification(self, user: User) -> None:
        if user.email_verified:
            return
        token = await self._issue_token(user, EmailTokenPurpose.VERIFY, VERIFY_TOKEN_TTL)
        await self._db.commit()
        await self._mailer.send(
            messages.verify_email(user.email, user.name, self._link("verify", token))
        )

    # --- Sign-in ---------------------------------------------------------------------

    async def authenticate(
        self, email: str, password: str, second_factor: str | None, actor: Actor
    ) -> User:
        user = await self._user_by_email(email)
        if user is None:
            await self._passwords.burn_time(password)
            audit.record(self._db, "auth.login.failure", actor, after={"reason": "unknown_account"})
            await self._db.commit()
            raise InvalidCredentialsError
        if user.locked_until is not None and user.locked_until > _now():
            # Same answer and cost as a wrong password; the owner was emailed at lock time.
            await self._passwords.burn_time(password)
            audit.record(
                self._db, "auth.login.failure", actor, user_id=user.id, after={"reason": "locked"}
            )
            await self._db.commit()
            raise InvalidCredentialsError
        if not await self._passwords.verify(user.password_hash, password):
            await self._record_failure(user, actor, "wrong_password")
            raise InvalidCredentialsError
        if user.disabled_at is not None:
            audit.record(
                self._db, "auth.login.failure", actor, user_id=user.id, after={"reason": "disabled"}
            )
            await self._db.commit()
            raise AccountDisabledError
        if user.totp_enabled:
            if not second_factor:
                raise SecondFactorRequiredError
            if not await self._two_factor.verify(user, second_factor, actor):
                await self._record_failure(user, actor, "wrong_second_factor")
                raise InvalidSecondFactorError
        if self._passwords.needs_rehash(user.password_hash):
            user.password_hash = await self._passwords.hash(password)
        user.failed_login_count = 0
        user.locked_until = None
        audit.record(self._db, "auth.login.success", actor, user_id=user.id)
        await self._db.commit()
        await self._db.refresh(user)
        return user

    async def _record_failure(self, user: User, actor: Actor, reason: str) -> None:
        failures = await self._db.scalar(
            update(User)
            .where(User.id == user.id)
            .values(failed_login_count=User.failed_login_count + 1)
            .returning(User.failed_login_count)
        )
        audit.record(
            self._db, "auth.login.failure", actor, user_id=user.id, after={"reason": reason}
        )
        locked = failures is not None and failures >= MAX_FAILED_SIGN_INS
        if locked:
            await self._db.execute(
                update(User)
                .where(User.id == user.id)
                .values(locked_until=_now() + LOCKOUT, failed_login_count=0)
            )
            audit.record(
                self._db,
                "auth.lockout",
                actor,
                user_id=user.id,
                after={"minutes": LOCKOUT.seconds // 60},
            )
        await self._db.commit()
        if locked:
            await self._mailer.send(
                messages.account_locked(
                    user.email, user.name, LOCKOUT.seconds // 60, self._link("forgot")
                )
            )

    # --- Passwords -------------------------------------------------------------------

    async def check_password(self, password: str, *, email: str) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise WeakPasswordError(f"Use at least {MIN_PASSWORD_LENGTH} characters.")
        if len(password) > MAX_PASSWORD_LENGTH:
            raise WeakPasswordError(f"Use at most {MAX_PASSWORD_LENGTH} characters.")
        if password.strip().lower() in {email.lower(), email.split("@")[0].lower()}:
            raise WeakPasswordError("Choose a password that is not your email address.")
        if self._settings.password_breach_check and await is_breached(password, self._http):
            raise WeakPasswordError(
                "This password has appeared in a known data breach. Choose a different one."
            )

    async def request_password_reset(self, email: str, actor: Actor) -> None:
        user = await self._user_by_email(email)
        if user is None:
            return
        token = await self._issue_token(user, EmailTokenPurpose.RESET, RESET_TOKEN_TTL)
        audit.record(self._db, "auth.password.reset_requested", actor, user_id=user.id)
        await self._db.commit()
        await self._mailer.send(
            messages.reset_password(user.email, user.name, self._link("reset", token))
        )

    async def reset_password(self, token: str, new_password: str, actor: Actor) -> None:
        email_token = await self._claim_token(token, EmailTokenPurpose.RESET)
        user = await self._db.get_one(User, email_token.user_id)
        await self.check_password(new_password, email=user.email)
        user.password_hash = await self._passwords.hash(new_password)
        user.failed_login_count = 0
        user.locked_until = None
        # Following the emailed link proves the address, too.
        user.email_verified_at = user.email_verified_at or _now()
        audit.record(self._db, "auth.password.reset", actor, user_id=user.id)
        await self._db.commit()
        await self._sessions.delete_all(user.id)
        await self._mailer.send(messages.password_changed(user.email, user.name))

    async def change_password(
        self, user: User, current: str, new: str, keep_session: str | None, actor: Actor
    ) -> None:
        if not await self._passwords.verify(user.password_hash, current):
            raise IncorrectPasswordError("Your current password is incorrect.")
        await self.check_password(new, email=user.email)
        user.password_hash = await self._passwords.hash(new)
        audit.record(self._db, "auth.password.changed", actor, user_id=user.id)
        await self._db.commit()
        await self._sessions.delete_all(user.id, keep=keep_session)
        await self._mailer.send(messages.password_changed(user.email, user.name))

    async def notify_two_factor_changed(self, user: User, *, enabled: bool) -> None:
        await self._mailer.send(messages.two_factor_changed(user.email, user.name, enabled=enabled))

    # --- Administrators --------------------------------------------------------------

    async def create_admin(
        self, *, name: str, email: str, password: str, actor: Actor, only_if_first: bool
    ) -> User:
        """A verified instance administrator. Single-user mode's first-run setup passes
        `only_if_first` (guide 8.1: one admin, no email); `make create-admin` does not."""
        if only_if_first and await self._any_user():
            raise RegistrationClosedError("This Winnow instance already has its administrator.")
        if await self._user_by_email(email) is not None:
            raise RegistrationClosedError("An account with this email already exists.")
        await self.check_password(password, email=email)
        user = User(
            name=name,
            email=email,
            password_hash=await self._passwords.hash(password),
            email_verified_at=_now(),
            is_instance_admin=True,
        )
        self._db.add(user)
        await self._db.flush()
        audit.record(self._db, "auth.admin_created", actor, user_id=user.id)
        await self._db.commit()
        await self._db.refresh(user)
        return user

    # --- Helpers ---------------------------------------------------------------------

    async def _notify_existing_account(self, user: User, actor: Actor) -> None:
        audit.record(self._db, "auth.register.existing_account", actor, user_id=user.id)
        await self._db.commit()
        await self._mailer.send(
            messages.account_exists(user.email, user.name, self._link("forgot"))
        )

    async def _any_user(self) -> bool:
        return bool(await self._db.scalar(select(func.count()).select_from(User)))

    async def _user_by_email(self, email: str) -> User | None:
        user: User | None = await self._db.scalar(
            select(User).where(User.email == email.strip(), User.deleted_at.is_(None))
        )
        return user

    async def _issue_token(self, user: User, purpose: EmailTokenPurpose, ttl: timedelta) -> str:
        """A fresh one-time token; earlier unused tokens for the same purpose stop working."""
        await self._db.execute(
            update(EmailToken)
            .where(
                EmailToken.user_id == user.id,
                EmailToken.purpose == purpose,
                EmailToken.used_at.is_(None),
            )
            .values(used_at=_now())
        )
        token = new_token()
        self._db.add(
            EmailToken(
                user_id=user.id,
                purpose=purpose,
                token_hash=hash_token(token),
                expires_at=_now() + ttl,
            )
        )
        return token

    async def _claim_token(self, token: str, purpose: EmailTokenPurpose) -> EmailToken:
        """Mark a valid token used, atomically, so a link works exactly once. The claim
        commits with the caller's change; if that change fails, the link still works."""
        claimed = await self._db.scalar(
            update(EmailToken)
            .where(
                EmailToken.token_hash == hash_token(token),
                EmailToken.purpose == purpose,
                EmailToken.used_at.is_(None),
                EmailToken.expires_at > _now(),
            )
            .values(used_at=_now())
            .returning(EmailToken)
        )
        if claimed is None:
            raise InvalidTokenError
        return claimed

    def _link(self, page: str, token: str | None = None) -> str:
        return f"{self._settings.public_origin}/{page}" + (f"/{token}" if token else "")
