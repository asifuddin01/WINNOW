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


def project_invite(
    to: str, *, inviter: str, project_title: str, role: str, link: str, days: int
) -> Email:
    """The review's title stays in the body: a subject line is a header, and titles are
    typed by people."""
    return Email(
        to,
        "You are invited to a review on Winnow",
        f"Hi,\n\n{inviter} invited you to join the review “{project_title}” on Winnow as "
        f"{'an' if role[0] in 'aeiou' else 'a'} {role}.\n\nOpen this link to accept:\n\n{link}"
        f"\n\nThe link expires in {days} days and works for a Winnow account with this email "
        f"address ({to}). If you do not have an account yet, the link lets you create one."
        + SIGNATURE,
    )


def discussion_requested(to: str, *, asker: str, project_title: str, link: str) -> Email:
    """Guide 8.7's "Discuss": the reviewers of a record in conflict are asked to talk.

    The record's title stays out of the email: the link opens it for a signed-in member.
    """
    return Email(
        to,
        "A record in your review needs a discussion",
        f"Hi,\n\n{asker} would like to discuss a record you screened in the review "
        f"“{project_title}” on Winnow, where the reviewers' decisions differ. They left a note "
        f"on it.\n\nOpen it here:\n\n{link}" + SIGNATURE,
    )


def pdf_quarantined(to: str, *, project_title: str, signature: str, link: str) -> Email:
    """Guide 12.4: a PDF the scanner flagged is quarantined and the review's owners and
    admins are told. The file's name stays out of the email; names are typed by people."""
    return Email(
        to,
        "A PDF in your review was quarantined",
        f"Hi,\n\nA PDF uploaded to the review “{project_title}” on Winnow was flagged by the "
        f"virus scanner ({signature}). It has been moved to quarantine: nobody can open or "
        "download it, and the record shows that its PDF was quarantined.\n\nIf you expected "
        f"this file to be safe, get a fresh copy from the publisher.\n\n{link}" + SIGNATURE,
    )
