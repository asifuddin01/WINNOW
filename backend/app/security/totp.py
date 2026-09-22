"""RFC 6238 time-based one-time passwords and single-use recovery codes (guide 8.1, 12.1)."""

import base64
import hmac
import secrets
import time

import pyotp
import segno

from app.security.tokens import keyed_hash

STEP_SECONDS = 30
DIGITS = 6
TOLERANCE_STEPS = 1  # accept the previous and next 30-second window for clock drift
ISSUER = "Winnow"
RECOVERY_CODE_COUNT = 10
# No 0/o, 1/l/i: recovery codes get typed from paper.
RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def new_secret() -> str:
    """160 random bits, base32, as authenticator apps expect."""
    return pyotp.random_base32()


def provisioning_uri(secret: str, account: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=ISSUER)


def qr_data_uri(uri: str) -> str:
    """The provisioning URI as an SVG QR code, inline so no request leaves the page."""
    svg = segno.make(uri, error="m").svg_inline(scale=5, border=2, dark="#000", light="#fff")
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def matching_step(
    secret: str, code: str, last_used_step: int | None, now: float | None = None
) -> int | None:
    """The time step `code` belongs to, or None. Steps at or before `last_used_step` are
    rejected, so an intercepted code cannot be replayed within its window."""
    code = code.replace(" ", "").strip()
    if len(code) != DIGITS or not code.isdigit():
        return None
    totp = pyotp.TOTP(secret, digits=DIGITS, interval=STEP_SECONDS)
    current = int((time.time() if now is None else now) // STEP_SECONDS)
    for step in range(current - TOLERANCE_STEPS, current + TOLERANCE_STEPS + 1):
        if last_used_step is not None and step <= last_used_step:
            continue
        if hmac.compare_digest(totp.at(step * STEP_SECONDS), code):
            return step
    return None


def new_recovery_codes() -> list[str]:
    def one() -> str:
        chars = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(10))
        return f"{chars[:5]}-{chars[5:]}"

    return [one() for _ in range(RECOVERY_CODE_COUNT)]


def normalize_recovery_code(code: str) -> str:
    return code.replace("-", "").replace(" ", "").strip().lower()


def hash_recovery_code(key: bytes, code: str) -> str:
    """Codes carry ~50 bits of entropy and are single-use, so a keyed hash is enough;
    Argon2 would make checking ten of them per sign-in needlessly slow."""
    return keyed_hash(key, "recovery:" + normalize_recovery_code(code))


def looks_like_recovery_code(code: str) -> bool:
    return len(normalize_recovery_code(code)) == 10
