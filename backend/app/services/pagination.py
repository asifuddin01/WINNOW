"""Opaque cursors for keyset pagination (guide 10: `?cursor=&limit=`, at most 200)."""

import base64
import binascii
import json

from app.services.errors import InvalidCursorError

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def encode_cursor(*values: str) -> str:
    """The sort key of the last item on a page, for the page after it."""
    return base64.urlsafe_b64encode(json.dumps(values).encode()).decode().rstrip("=")


def decode_cursor(cursor: str, arity: int) -> list[str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        values = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise InvalidCursorError from None
    if (
        not isinstance(values, list)
        or len(values) != arity
        or not all(isinstance(value, str) for value in values)
    ):
        raise InvalidCursorError
    return values
