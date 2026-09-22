"""Request and response bodies for /auth. String fields carry maximum lengths (guide 12.3)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

Password = str  # length rules live in the account service, which explains them to people
PASSWORD_FIELD = Field(min_length=1, max_length=256)
CODE_FIELD = Field(min_length=1, max_length=32)


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr = Field(max_length=254)
    password: Password = PASSWORD_FIELD
    # Needed on instances where registration is by invitation only.
    invite_token: str | None = Field(default=None, min_length=16, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr = Field(max_length=254)
    password: Password = PASSWORD_FIELD
    # A 6-digit authenticator code or a recovery code, once the server asks for one.
    totp: str | None = Field(default=None, max_length=32)


class EmailRequest(BaseModel):
    email: EmailStr = Field(max_length=254)


class TokenRequest(BaseModel):
    token: str = Field(min_length=16, max_length=128)


class ResetPasswordRequest(TokenRequest):
    password: Password = PASSWORD_FIELD


class ChangePasswordRequest(BaseModel):
    current_password: Password = PASSWORD_FIELD
    new_password: Password = PASSWORD_FIELD


class CodeRequest(BaseModel):
    code: str = CODE_FIELD


class DisableTwoFactorRequest(BaseModel):
    password: Password = PASSWORD_FIELD
    code: str = CODE_FIELD


class UserOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    email_verified: bool
    totp_enabled: bool
    recovery_codes_left: int
    is_instance_admin: bool
    has_password: bool
    google_linked: bool
    created_at: datetime


class CsrfOut(BaseModel):
    csrf_token: str


class SignedIn(CsrfOut):
    user: UserOut


class Accepted(BaseModel):
    status: Literal["accepted"] = "accepted"
    detail: str


class AuthOptions(BaseModel):
    """What this instance offers: shown on the sign-in pages, and used by project
    settings to hide what the instance cannot do."""

    registration: Literal["open", "invite_only", "closed"]
    single_user: bool
    needs_setup: bool
    email_enabled: bool
    google_enabled: bool
    llm_available: bool
    owner_two_factor_required: bool


class SessionOut(BaseModel):
    id: str
    created_at: datetime
    last_seen_at: datetime
    ip: str | None
    user_agent: str | None
    current: bool


class TwoFactorSetupOut(BaseModel):
    secret: str
    otpauth_uri: str
    qr_code: str


class RecoveryCodesOut(BaseModel):
    recovery_codes: list[str]


class TwoFactorEnabled(RecoveryCodesOut, CsrfOut):
    pass


class GoogleSignedIn(SignedIn):
    """A Google sign-in finished with a second factor; `redirect` is where it started."""

    redirect: str
