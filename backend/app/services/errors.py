"""Domain errors. Services raise these; the API turns each into a problem response.

Each carries the HTTP status and a stable `code` the frontend can switch on. Messages are
written for the person reading them and never reveal whether an account exists.
"""

from typing import ClassVar


class DomainError(Exception):
    status: ClassVar[int] = 400
    code: ClassVar[str] = "invalid_request"
    message: ClassVar[str] = "The request could not be completed."

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail or self.message)
        self.detail = detail or self.message


class InvalidCredentialsError(DomainError):
    status = 401
    code = "invalid_credentials"
    message = "Email or password is incorrect."


class SecondFactorRequiredError(DomainError):
    status = 401
    code = "totp_required"
    message = "Enter the code from your authenticator app."


class InvalidSecondFactorError(DomainError):
    status = 401
    code = "invalid_totp"
    message = "That code is not valid. Codes change every 30 seconds; try the current one."


class NotAuthenticatedError(DomainError):
    status = 401
    code = "not_authenticated"
    message = "Sign in to continue."


class InvalidTokenError(DomainError):
    status = 400
    code = "invalid_token"
    message = "This link is invalid or has expired. Request a new one."


class WeakPasswordError(DomainError):
    status = 422
    code = "weak_password"


class RegistrationClosedError(DomainError):
    status = 403
    code = "registration_closed"
    message = "Registration is closed on this Winnow instance."


class TwoFactorStateError(DomainError):
    status = 409
    code = "two_factor_state"
