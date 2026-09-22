"""Sign in with Google: OpenID Connect, authorization code flow with PKCE.

The browser is sent to Google with a one-time `state` (bound to it by a cookie, so nobody
can finish a sign-in they did not start), a `nonce` (so an ID token cannot be replayed into
another sign-in) and a PKCE challenge (so an intercepted code is useless). Google's ID
token is checked against its published signing keys, issuer, audience and expiry.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from redis.asyncio import Redis

from app.security.tokens import hash_token

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - an endpoint, not a secret
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")
PROVIDER = "google"
KEYS_TTL_SECONDS = 3600


class GoogleSignInError(Exception):
    """A sign-in that must not go ahead. `code` is shown to the person as a message."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class GoogleProfile:
    subject: str
    email: str
    name: str


def pkce_pair() -> tuple[str, str]:
    """A PKCE verifier and its S256 challenge (RFC 7636)."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def authorization_url(
    client_id: str, redirect_uri: str, state: str, nonce: str, code_challenge: str
) -> str:
    return (
        AUTHORIZE_URL
        + "?"
        + urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "prompt": "select_account",
            }
        )
    )


class GoogleClient:
    def __init__(self, http: httpx.AsyncClient, client_id: str, client_secret: str) -> None:
        self._http = http
        self._client_id = client_id
        self._client_secret = client_secret
        self._keys: dict[str, jwt.PyJWK] = {}
        self._keys_expire = 0.0

    async def exchange(self, code: str, verifier: str, redirect_uri: str) -> str:
        """Trade the authorization code for an ID token."""
        try:
            response = await self._http.post(
                TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": verifier,
                },
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            raise GoogleSignInError("google_failed") from exc
        body: dict[str, Any] = response.json() if response.is_success else {}
        id_token = body.get("id_token")
        if not isinstance(id_token, str):
            raise GoogleSignInError("google_failed")
        return id_token

    async def verify(self, id_token: str, nonce: str) -> GoogleProfile:
        """Check signature, issuer, audience, expiry and nonce; require a verified email."""
        try:
            kid = jwt.get_unverified_header(id_token).get("kid")
            key = await self._key(kid)
            claims: dict[str, Any] = jwt.decode(
                id_token,
                key=key,
                algorithms=["RS256"],
                audience=self._client_id,
                issuer=ISSUERS,
                leeway=60,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except (jwt.PyJWTError, httpx.HTTPError, KeyError, ValueError) as exc:
            raise GoogleSignInError("google_failed") from exc
        if claims.get("azp", self._client_id) != self._client_id:
            raise GoogleSignInError("google_failed")
        if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
            raise GoogleSignInError("google_failed")
        email = claims.get("email")
        if not isinstance(email, str) or claims.get("email_verified") is not True:
            raise GoogleSignInError("google_unverified")
        name = claims.get("name")
        return GoogleProfile(
            subject=str(claims["sub"]),
            email=email,
            name=name if isinstance(name, str) and name.strip() else email.split("@")[0],
        )

    async def _key(self, kid: object) -> jwt.PyJWK:
        if not isinstance(kid, str):
            raise KeyError("token has no key id")
        if kid not in self._keys or time.monotonic() > self._keys_expire:
            # Google rotates its keys; an unknown id means it is time to fetch again.
            response = await self._http.get(JWKS_URL, timeout=10.0)
            response.raise_for_status()
            key_set = jwt.PyJWKSet.from_dict(response.json())
            self._keys = {key.key_id: key for key in key_set.keys if key.key_id}
            self._keys_expire = time.monotonic() + KEYS_TTL_SECONDS
        return self._keys[kid]


class OneTimeStore:
    """Short-lived, single-use records in Redis, keyed by the hash of a random token."""

    def __init__(self, redis: Redis, prefix: str, ttl_seconds: int) -> None:
        self._redis = redis
        self._prefix = prefix
        self._ttl = ttl_seconds

    async def create(self, data: dict[str, str]) -> str:
        token = secrets.token_urlsafe(32)
        await self._redis.set(self._key(token), json.dumps(data), ex=self._ttl)
        return token

    async def peek(self, token: str) -> dict[str, str] | None:
        raw: str | None = await self._redis.get(self._key(token))
        return json.loads(raw) if raw else None

    async def take(self, token: str) -> dict[str, str] | None:
        """Read and delete in one step: a second use finds nothing."""
        raw: str | None = await self._redis.getdel(self._key(token))
        return json.loads(raw) if raw else None

    async def discard(self, token: str) -> None:
        await self._redis.delete(self._key(token))

    def _key(self, token: str) -> str:
        return f"{self._prefix}:{hash_token(token)}"
