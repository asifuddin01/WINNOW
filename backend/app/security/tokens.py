"""Random secrets for links and sessions. Only their SHA-256 is ever stored."""

import hashlib
import hmac
import secrets


def new_token() -> str:
    """256 bits, URL-safe."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def keyed_hash(key: bytes, value: str) -> str:
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()
