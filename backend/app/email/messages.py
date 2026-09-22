"""The emails Winnow sends. Plain text only: nothing to render, nothing to inject."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Email:
    to: str
    subject: str
    body: str


SIGNATURE = "\n\n— Winnow\nIf you did not expect this email, you can ignore it."


def verify_email(to: str, name: str, link: str) -> Email:
    return Email(
        to,
        "Confirm your email for Winnow",
        f"Hi {name},\n\nConfirm your email address to start working on reviews:\n\n{link}\n\n"
        "The link works once and expires in 24 hours." + SIGNATURE,
    )


def account_exists(to: str, name: str, reset_link: str) -> Email:
    """Sent instead of an error when someone registers with an existing address, so the
    sign-up form never reveals which emails have accounts."""
    return Email(
        to,
        "You already have a Winnow account",
        f"Hi {name},\n\nSomeone tried to create a Winnow account with this email address, "
        "which already has one. If that was you, sign in instead, or reset your password:"
        f"\n\n{reset_link}" + SIGNATURE,
    )


def reset_password(to: str, name: str, link: str) -> Email:
    return Email(
        to,
        "Reset your Winnow password",
        f"Hi {name},\n\nUse this link to choose a new password:\n\n{link}\n\n"
        "The link works once and expires in 30 minutes. Your current password keeps working "
        "until you change it." + SIGNATURE,
    )


def account_locked(to: str, name: str, minutes: int, reset_link: str) -> Email:
    return Email(
        to,
        "Sign-in to Winnow paused",
        f"Hi {name},\n\nAfter repeated failed sign-in attempts we paused sign-in to your "
        f"account for {minutes} minutes. If this was not you, reset your password now:\n\n"
        f"{reset_link}" + SIGNATURE,
    )


def password_changed(to: str, name: str) -> Email:
    return Email(
        to,
        "Your Winnow password was changed",
        f"Hi {name},\n\nThe password for your Winnow account was just changed, and every "
        "other device was signed out. If you did not do this, reset your password straight "
        "away." + SIGNATURE,
    )


def two_factor_changed(to: str, name: str, *, enabled: bool) -> Email:
    state = "turned on" if enabled else "turned off"
    return Email(
        to,
        f"Two-factor authentication {state}",
        f"Hi {name},\n\nTwo-factor authentication was {state} for your Winnow account. "
        "If you did not do this, reset your password straight away." + SIGNATURE,
    )
