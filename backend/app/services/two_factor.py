"""TOTP two-factor authentication: setup, enabling, checking codes, recovery codes."""

from dataclasses import dataclass

from sqlalchemy import Text, any_, func, literal, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import User
from app.security import crypto, totp
from app.security.passwords import Passwords
from app.services import audit
from app.services.audit import Actor
from app.services.errors import InvalidSecondFactorError, TwoFactorStateError


@dataclass(frozen=True, slots=True)
class TwoFactorSetup:
    secret: str
    otpauth_uri: str
    qr_code: str  # data: URI of an SVG


class IncorrectPasswordError(TwoFactorStateError):
    status = 422
    code = "incorrect_password"
    message = "Your password is incorrect."


class TwoFactorService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db = db
        self._encryption_key = settings.encryption_key_bytes
        self._recovery_key = settings.secret_key.get_secret_value().encode() + b"|recovery-codes"

    async def begin_setup(self, user: User) -> TwoFactorSetup:
        """Store a new, not-yet-enabled secret and return what the authenticator app needs."""
        if user.totp_enabled:
            raise TwoFactorStateError("Two-factor authentication is already on.")
        secret = totp.new_secret()
        user.totp_secret_enc = crypto.encrypt(self._encryption_key, secret.encode(), user.id.bytes)
        user.totp_last_step = None
        await self._db.commit()
        uri = totp.provisioning_uri(secret, user.email)
        return TwoFactorSetup(secret=secret, otpauth_uri=uri, qr_code=totp.qr_data_uri(uri))

    async def enable(self, user: User, code: str, actor: Actor) -> list[str]:
        """Turn 2FA on once the app proves it has the secret. Returns the recovery codes,
        which are shown once and stored only as keyed hashes."""
        if user.totp_enabled:
            raise TwoFactorStateError("Two-factor authentication is already on.")
        if user.totp_secret_enc is None:
            raise TwoFactorStateError("Start two-factor setup first.")
        step = totp.matching_step(self._secret(user), code, None)
        if step is None:
            raise InvalidSecondFactorError
        codes = totp.new_recovery_codes()
        user.totp_enabled = True
        user.totp_last_step = step
        user.recovery_codes_hash = [totp.hash_recovery_code(self._recovery_key, c) for c in codes]
        audit.record(self._db, "auth.2fa.enabled", actor, user_id=user.id)
        await self._db.commit()
        return codes

    async def disable(
        self, user: User, password: str, code: str, passwords: Passwords, actor: Actor
    ) -> None:
        if not user.totp_enabled:
            raise TwoFactorStateError("Two-factor authentication is already off.")
        if not await passwords.verify(user.password_hash, password):
            raise IncorrectPasswordError
        if not await self.verify(user, code, actor):
            raise InvalidSecondFactorError
        await self._db.refresh(user)
        user.totp_enabled = False
        user.totp_secret_enc = None
        user.totp_last_step = None
        user.recovery_codes_hash = []
        audit.record(self._db, "auth.2fa.disabled", actor, user_id=user.id)
        await self._db.commit()

    async def regenerate_recovery_codes(self, user: User, code: str, actor: Actor) -> list[str]:
        if not user.totp_enabled:
            raise TwoFactorStateError("Turn on two-factor authentication first.")
        if not await self.verify(user, code, actor):
            raise InvalidSecondFactorError
        await self._db.refresh(user)
        codes = totp.new_recovery_codes()
        user.recovery_codes_hash = [totp.hash_recovery_code(self._recovery_key, c) for c in codes]
        audit.record(self._db, "auth.2fa.recovery_codes_regenerated", actor, user_id=user.id)
        await self._db.commit()
        return codes

    async def verify(self, user: User, code: str, actor: Actor) -> bool:
        """Accept a current TOTP code or an unused recovery code. Both are claimed with a
        conditional UPDATE, so two requests racing with the same code cannot both win.
        Does not commit; the caller's transaction does."""
        if not user.totp_enabled or user.totp_secret_enc is None:
            return False
        step = totp.matching_step(self._secret(user), code, user.totp_last_step)
        if step is not None:
            claimed = await self._db.scalar(
                update(User)
                .where(
                    User.id == user.id,
                    or_(User.totp_last_step.is_(None), User.totp_last_step < step),
                )
                .values(totp_last_step=step)
                .returning(User.id)
            )
            return claimed is not None
        if totp.looks_like_recovery_code(code):
            digest = totp.hash_recovery_code(self._recovery_key, code)
            # Bound as text: array_remove(text[], varchar) does not exist in PostgreSQL.
            code_hash = literal(digest, Text)
            claimed = await self._db.scalar(
                update(User)
                .where(User.id == user.id, code_hash == any_(User.recovery_codes_hash))
                .values(recovery_codes_hash=func.array_remove(User.recovery_codes_hash, code_hash))
                .returning(User.id)
            )
            if claimed is not None:
                audit.record(self._db, "auth.2fa.recovery_code_used", actor, user_id=user.id)
                return True
        return False

    def _secret(self, user: User) -> str:
        if user.totp_secret_enc is None:
            raise TwoFactorStateError("Start two-factor setup first.")
        return crypto.decrypt(self._encryption_key, user.totp_secret_enc, user.id.bytes).decode()
