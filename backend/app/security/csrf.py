"""CSRF protection (guide 12.1): a signed double-submit token plus an Origin check.

`GET /auth/csrf` sets a random nonce in an HttpOnly cookie and returns
HMAC(SECRET_KEY, nonce + session). The SPA keeps the token in memory and sends it as
X-CSRF-Token on every write. Another site can neither read the token nor set our
__Host- cookies, and the token stops working when the session changes.
"""

import hmac
import secrets

from app.security.tokens import keyed_hash

CSRF_COOKIE = "__Host-winnow_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def new_nonce() -> str:
    return secrets.token_urlsafe(32)


def csrf_token(secret_key: bytes, nonce: str, session_key: str | None) -> str:
    return keyed_hash(secret_key, f"csrf|{nonce}|{session_key or ''}")


def token_is_valid(
    secret_key: bytes, nonce: str | None, session_key: str | None, presented: str | None
) -> bool:
    if not nonce or not presented:
        return False
    return hmac.compare_digest(csrf_token(secret_key, nonce, session_key), presented)
