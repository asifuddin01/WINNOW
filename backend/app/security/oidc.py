"""OpenID Connect sign-in, shared by Google and ORCID: authorization code flow.

The browser is sent to the provider with a one-time `state` (bound to it by a cookie, so
nobody can finish a sign-in they did not start) and a `nonce` (so an ID token cannot be
replayed into another sign-in, nor a code from someone else's sign-in swapped in). The ID
token is checked against the provider's published signing keys, issuer, audience and
expiry.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

import httpx
import jwt
from redis.asyncio import Redis

from app.security.tokens import hash_token

KEYS_TTL_SECONDS = 3600


class SignInError(Exception):
    """A sign-in that must not go ahead. `code` is shown to the person as a message."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def pkce_pair() -> tuple[str, str]:
    """A PKCE verifier and its S256 challenge (RFC 7636)."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class OidcClient:
    """Trades a code for an ID token and checks it. Subclasses turn claims into a profile."""

    provider: str

    def __init__(
        self,
        http: httpx.AsyncClient,
        client_id: str,
        client_secret: str,
        *,
        token_url: str,
        jwks_url: str,
        issuers: tuple[str, ...],
    ) -> None:
        self._http = http
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = token_url
        self._jwks_url = jwks_url
        self._issuers = issuers
        self._keys: dict[str, jwt.PyJWK] = {}
        self._keys_expire = 0.0

    def failed(self) -> SignInError:
        return SignInError(f"{self.provider}_failed")

    async def exchange(self, code: str, redirect_uri: str, **extra: str) -> str:
        """Trade the authorization code for an ID token."""
        try:
            response = await self._http.post(
                self._token_url,
                data={
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                    **extra,
                },
                headers={"Accept": "application/json"},
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            raise self.failed() from exc
        body: dict[str, Any] = response.json() if response.is_success else {}
        id_token = body.get("id_token")
        if not isinstance(id_token, str):
            raise self.failed()
        return id_token

    async def claims(self, id_token: str, nonce: str) -> dict[str, Any]:
        """The token's claims, once signature, issuer, audience, expiry and nonce check out."""
        try:
            kid = jwt.get_unverified_header(id_token).get("kid")
            key = await self._key(kid)
            claims: dict[str, Any] = jwt.decode(
                id_token,
                key=key,
                algorithms=["RS256"],
                audience=self._client_id,
                issuer=self._issuers,
                leeway=60,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except (jwt.PyJWTError, httpx.HTTPError, KeyError, ValueError) as exc:
            raise self.failed() from exc
        if claims.get("azp", self._client_id) != self._client_id:
            raise self.failed()
        if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
            raise self.failed()
        return claims

    async def _key(self, kid: object) -> jwt.PyJWK:
        if not isinstance(kid, str):
            raise KeyError("token has no key id")
        if kid not in self._keys or time.monotonic() > self._keys_expire:
            # Providers rotate their keys; an unknown id means it is time to fetch again.
            response = await self._http.get(self._jwks_url, timeout=10.0)
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
