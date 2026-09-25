"""Accounts and the one-time email tokens that verify them or reset their passwords."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, Timestamps, UUIDPrimaryKey

# Stored instead of a hash for accounts created through Google. It is not a valid Argon2
# hash, so password sign-in fails closed until the owner sets a password by email link.
NO_PASSWORD = "!"  # noqa: S105 - a marker, not a password


class User(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # AES-256-GCM ciphertext of the TOTP secret. Set but not enabled while 2FA is being
    # set up; totp_last_step blocks replaying a code inside its window (guide 12.1).
    totp_secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger)
    recovery_codes_hash: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )

    orcid: Mapped[str | None] = mapped_column(Text)
    is_instance_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set by an instance administrator (guide 8.18): the account cannot sign in until
    # enabled again; its reviews and work are untouched.
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None

    @property
    def recovery_codes_left(self) -> int:
        return len(self.recovery_codes_hash or [])

    @property
    def has_password(self) -> bool:
        """False for accounts created through Google until they set one by email link."""
        return self.password_hash != NO_PASSWORD


class EmailTokenPurpose(enum.StrEnum):
    VERIFY = "verify"
    RESET = "reset"
    INVITE = "invite"


class EmailToken(UUIDPrimaryKey, CreatedAt, Base):
    """Only the SHA-256 of a token is stored; the token itself exists in one email."""

    __tablename__ = "email_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[EmailTokenPurpose] = mapped_column(
        Enum(
            EmailTokenPurpose,
            name="email_token_purpose",
            values_callable=lambda e: [m.value for m in e],
        )
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserIdentity(UUIDPrimaryKey, CreatedAt, Base):
    """An outside account (today: Google) that can sign in as a Winnow user."""

    __tablename__ = "user_identities"
    __table_args__ = (UniqueConstraint("provider", "subject"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    # The provider's stable id for the person ("sub"); emails can change, this cannot.
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
