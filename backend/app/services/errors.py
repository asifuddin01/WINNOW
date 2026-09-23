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


# --- Projects -----------------------------------------------------------------------


class NotFoundError(DomainError):
    """Also what non-members get for a project, whether or not it exists (guide 7)."""

    status = 404
    code = "not_found"
    message = "We could not find that. It may have been deleted, or you may not have access."


class ForbiddenError(DomainError):
    status = 403
    code = "forbidden"
    message = "Your role in this review does not allow that."


class EmailUnverifiedError(DomainError):
    status = 403
    code = "email_unverified"
    message = "Confirm your email address first. We sent you a link when you signed up."


class OwnerTwoFactorRequiredError(DomainError):
    status = 403
    code = "two_factor_required"
    message = "Review owners on this Winnow instance must turn on two-factor authentication."


class InviteEmailMismatchError(DomainError):
    status = 403
    code = "invite_email_mismatch"
    message = "This invitation is for a different email address. Sign in with that address."


class ConflictError(DomainError):
    status = 409
    code = "conflict"


class AlreadyMemberError(ConflictError):
    code = "already_member"
    message = "That person is already a member of this review."


class DuplicateNameError(ConflictError):
    code = "duplicate"
    message = "There is already one with that name."


class OwnerProtectedError(ConflictError):
    code = "owner_protected"
    message = "The owner's role cannot change here. Transfer ownership instead."


class LimitReachedError(ConflictError):
    code = "limit_reached"


class InvitesUnavailableError(ConflictError):
    code = "invites_unavailable"
    message = "This Winnow instance is set up for a single user, so it has no invitations."


class FeatureUnavailableError(ConflictError):
    code = "feature_unavailable"


class InvalidCursorError(DomainError):
    code = "invalid_cursor"
    message = "That page link is out of date. Start again from the first page."


class InvalidPatternError(DomainError):
    status = 422
    code = "invalid_pattern"


class NotInClusterError(DomainError):
    status = 422
    code = "not_in_cluster"
    message = "That record is not in this group of duplicates."
