"""Have I Been Pwned range lookup (k-anonymity): only 5 hex characters of the password's
SHA-1 leave the server, and the response is padded so its size reveals nothing."""

import hashlib

import httpx
import structlog

log = structlog.get_logger(__name__)
RANGE_URL = "https://api.pwnedpasswords.com/range/{prefix}"


async def is_breached(password: str, client: httpx.AsyncClient) -> bool:
    """True if the password appears in a known breach. Fails open: an unreachable service
    must not stop people from registering or resetting passwords."""
    # The Pwned Passwords range API is defined on SHA-1; it is a lookup key, not protection.
    # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1
    digest = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    try:
        response = await client.get(
            RANGE_URL.format(prefix=prefix), headers={"Add-Padding": "true"}, timeout=3.0
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("password_breach_check.unavailable", error=type(exc).__name__)
        return False
    for line in response.text.splitlines():
        candidate, _, count = line.partition(":")
        if candidate == suffix and count.strip().isdigit() and int(count) > 0:
            return True
    return False
