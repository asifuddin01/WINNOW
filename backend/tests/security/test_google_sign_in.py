"""Sign in with Google against a fake Google that signs real RS256 ID tokens."""

import base64
import hashlib
import time
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pyotp
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import AsyncClient, Response
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.session_http import safe_redirect
from app.models import AuditLog, User, UserIdentity
from app.security.google import GoogleClient
from app.security.sessions import SESSION_COOKIE
from tests.auth_helpers import AUTH, PASSWORD, enable_two_factor, login, post, register, signed_in
from tests.conftest import MemoryMailer, make_client

CLIENT_ID = "winnow-test.apps.googleusercontent.com"
GOOGLE = f"{AUTH}/google"


class FakeGoogle:
    """Google's token and key endpoints, holding the signing key and checking PKCE."""

    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.claims: dict[str, Any] = {
            "sub": "google-sub-1",
            "email": "grace@example.org",
            "email_verified": True,
            "name": "Grace Hopper",
        }
        self.challenge = ""
        self.nonce = ""
        self.audience = CLIENT_ID
        self.signing_key: Any = self.key

    def remember(self, location: str) -> dict[str, str]:
        query = {k: v[0] for k, v in parse_qs(urlsplit(location).query).items()}
        self.challenge = query["code_challenge"]
        self.nonce = query["nonce"]
        return query

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/v3/certs":
            jwk = jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key(), as_dict=True)
            return httpx.Response(
                200, json={"keys": [{**jwk, "kid": "k1", "alg": "RS256", "use": "sig"}]}
            )
        form = parse_qs(request.content.decode())
        verifier = form["code_verifier"][0]
        digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
        if digest.decode() != self.challenge or form["code"] != ["auth-code"]:
            return httpx.Response(400, json={"error": "invalid_grant"})
        now = int(time.time())
        token = jwt.encode(
            {
                "iss": "https://accounts.google.com",
                "aud": self.audience,
                "iat": now,
                "exp": now + 300,
                "nonce": self.nonce,
                **self.claims,
            },
            self.signing_key,
            algorithm="RS256",
            headers={"kid": "k1"},
        )
        return httpx.Response(200, json={"id_token": token, "access_token": "unused"})


@pytest.fixture
async def google(db_app: FastAPI) -> AsyncIterator[FakeGoogle]:
    fake = FakeGoogle()
    settings = db_app.state.settings
    settings.google_client_id = CLIENT_ID
    settings.google_client_secret = SecretStr("test-client-secret")
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake.handle))
    db_app.state.google = GoogleClient(http, CLIENT_ID, "test-client-secret")
    yield fake
    await http.aclose()


async def start(
    client: AsyncClient, google: FakeGoogle, redirect: str | None = None
) -> dict[str, str]:
    params = {"redirect": redirect} if redirect else None
    response = await client.get(f"{GOOGLE}/start", params=params)
    assert response.status_code == 303
    return google.remember(response.headers["location"])


async def callback(client: AsyncClient, state: str, **extra: str) -> Response:
    return await client.get(
        f"{GOOGLE}/callback", params={"state": state, "code": "auth-code", **extra}
    )


async def sign_in_with_google(
    client: AsyncClient, google: FakeGoogle, redirect: str | None = None
) -> Response:
    query = await start(client, google, redirect)
    return await callback(client, query["state"])


async def test_start_sends_the_browser_to_google(
    db_client: AsyncClient, google: FakeGoogle
) -> None:
    response = await db_client.get(f"{GOOGLE}/start")
    location = urlsplit(response.headers["location"])
    assert (
        f"{location.scheme}://{location.netloc}{location.path}"
        == "https://accounts.google.com/o/oauth2/v2/auth"
    )
    query = parse_qs(location.query)
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == ["https://testserver/api/v1/auth/google/callback"]
    assert query["scope"] == ["openid email profile"]
    assert query["code_challenge_method"] == ["S256"]
    assert len(query["state"][0]) >= 40
    assert len(query["nonce"][0]) >= 30
    cookie = next(
        h for h in response.headers.get_list("set-cookie") if h.startswith("__Host-winnow_oauth=")
    )
    assert "httponly" in cookie.lower()
    assert "secure" in cookie.lower()
    assert "samesite=lax" in cookie.lower()


async def test_a_new_person_gets_a_verified_account(
    db_client: AsyncClient, google: FakeGoogle, db: AsyncSession
) -> None:
    response = await sign_in_with_google(db_client, google, "/account")
    assert response.status_code == 303
    assert response.headers["location"] == "/account"
    me = (await db_client.get(f"{AUTH}/me")).json()
    assert me["email"] == "grace@example.org"
    assert me["name"] == "Grace Hopper"
    assert me["email_verified"] is True
    assert me["google_linked"] is True
    assert me["has_password"] is False
    actions = set((await db.scalars(select(AuditLog.action))).all())
    assert {"auth.register", "auth.identity.linked", "auth.login.success"} <= actions
    # No password was ever set, so password sign-in fails like any wrong password.
    assert (await login(db_client, "grace@example.org", "!")).status_code == 401


async def test_an_existing_account_is_linked_by_email(
    db_client: AsyncClient, google: FakeGoogle, mailer: MemoryMailer, db: AsyncSession
) -> None:
    await register(db_client, "grace@example.org")  # unverified password account
    await sign_in_with_google(db_client, google)
    me = (await db_client.get(f"{AUTH}/me")).json()
    assert me["google_linked"] is True
    assert me["has_password"] is True
    assert me["email_verified"] is True  # Google verified the address
    assert await db.scalar(select(UserIdentity.subject)) == "google-sub-1"
    async with make_client(db_client._transport.app) as other:  # type: ignore[attr-defined]
        assert (await login(other, "grace@example.org", PASSWORD)).status_code == 200


async def test_the_google_id_wins_over_a_changed_email(
    db_client: AsyncClient, google: FakeGoogle, db: AsyncSession
) -> None:
    await sign_in_with_google(db_client, google)
    google.claims["email"] = "grace.hopper@example.org"
    await sign_in_with_google(db_client, google)
    assert await db.scalar(select(User.email)) == "grace@example.org"
    assert len((await db.scalars(select(User.id))).all()) == 1


async def test_sign_in_rotates_the_session(
    db_app: FastAPI, db_client: AsyncClient, google: FakeGoogle
) -> None:
    db_client.cookies.set(SESSION_COOKIE, "attacker-chosen-session-id")
    response = await sign_in_with_google(db_client, google)
    issued = next(
        h for h in response.headers.get_list("set-cookie") if h.startswith(f"{SESSION_COOKIE}=")
    )
    assert "attacker-chosen-session-id" not in issued


@pytest.mark.parametrize("mode", ["wrong_cookie", "no_cookie"])
async def test_a_state_not_bound_to_this_browser_is_refused(
    db_app: FastAPI, db_client: AsyncClient, google: FakeGoogle, mode: str
) -> None:
    """Login CSRF: an attacker cannot make a victim's browser finish the attacker's sign-in."""
    query = await start(db_client, google)
    async with make_client(db_app) as victim:
        if mode == "wrong_cookie":
            victim.cookies.set("__Host-winnow_oauth", "something-else")
        response = await callback(victim, query["state"])
        assert response.headers["location"] == "/login?error=google_state"
        assert (await victim.get(f"{AUTH}/me")).status_code == 401


async def test_a_state_works_once(db_client: AsyncClient, google: FakeGoogle) -> None:
    query = await start(db_client, google)
    assert (await callback(db_client, query["state"])).headers["location"] == "/"
    db_client.cookies.set("__Host-winnow_oauth", query["state"])
    assert (await callback(db_client, query["state"])).headers[
        "location"
    ] == "/login?error=google_state"


async def test_cancelling_at_google(db_client: AsyncClient, google: FakeGoogle) -> None:
    query = await start(db_client, google)
    response = await db_client.get(
        f"{GOOGLE}/callback", params={"state": query["state"], "error": "access_denied"}
    )
    assert response.headers["location"] == "/login?error=google_cancelled"


@pytest.mark.parametrize(
    ("tamper", "expected"),
    [
        (lambda g: g.claims.update(email_verified=False), "google_unverified"),
        (lambda g: setattr(g, "audience", "someone-elses-app"), "google_failed"),
        (
            lambda g: setattr(
                g, "signing_key", rsa.generate_private_key(public_exponent=65537, key_size=2048)
            ),
            "google_failed",
        ),
    ],
    ids=["unverified-email", "wrong-audience", "forged-signature"],
)
async def test_untrustworthy_tokens_are_refused(
    db_client: AsyncClient, google: FakeGoogle, tamper: Any, expected: str
) -> None:
    tamper(google)
    response = await sign_in_with_google(db_client, google)
    assert response.headers["location"] == f"/login?error={expected}"
    assert (await db_client.get(f"{AUTH}/me")).status_code == 401


async def test_a_replayed_nonce_is_refused(db_client: AsyncClient, google: FakeGoogle) -> None:
    query = await start(db_client, google)
    google.nonce = "a-nonce-from-another-sign-in"
    response = await callback(db_client, query["state"])
    assert response.headers["location"] == "/login?error=google_failed"


async def test_open_redirects_are_refused(db_client: AsyncClient, google: FakeGoogle) -> None:
    response = await sign_in_with_google(db_client, google, "https://evil.example/")
    assert response.headers["location"] == "/"


async def test_closed_registration_still_lets_existing_accounts_in(
    db_app: FastAPI, db_client: AsyncClient, google: FakeGoogle, mailer: MemoryMailer
) -> None:
    db_app.state.settings.registration = "closed"
    response = await sign_in_with_google(db_client, google)
    assert response.headers["location"] == "/login?error=registration_closed"
    db_app.state.settings.registration = "open"
    await register(db_client, "grace@example.org")
    db_app.state.settings.registration = "closed"
    assert (await sign_in_with_google(db_client, google)).headers["location"] == "/"


async def test_two_factor_still_applies(
    db_app: FastAPI, db_client: AsyncClient, google: FakeGoogle, mailer: MemoryMailer
) -> None:
    await signed_in(db_client, mailer, "grace@example.org")
    otp, _ = await enable_two_factor(db_client)
    async with make_client(db_app) as laptop:
        response = await sign_in_with_google(laptop, google, "/account")
        assert response.headers["location"] == "/login?step=google-2fa"
        assert (await laptop.get(f"{AUTH}/me")).status_code == 401  # not signed in yet
        wrong = await post(laptop, "/google/two-factor", {"code": "000000"})
        assert wrong.status_code == 401
        assert wrong.json()["code"] == "invalid_totp"
        done = await post(laptop, "/google/two-factor", {"code": otp.at(int(time.time()) + 30)})
        assert done.status_code == 200
        assert done.json()["redirect"] == "/account"
        assert (await laptop.get(f"{AUTH}/me")).status_code == 200
        again = await post(
            laptop, "/google/two-factor", {"code": pyotp.TOTP(pyotp.random_base32()).now()}
        )
        assert again.json()["code"] == "google_pending_expired"


async def test_google_is_off_until_configured(db_client: AsyncClient) -> None:
    assert (await db_client.get(f"{AUTH}/options")).json()["google_enabled"] is False
    assert (await db_client.get(f"{GOOGLE}/start")).status_code == 404
    assert (await db_client.get(f"{GOOGLE}/callback", params={"state": "x"})).status_code == 404


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("/account", "/account"),
        (None, "/"),
        ("//evil.example", "/"),
        ("/\\evil", "/"),
        ("/login", "/"),
        ("/api/v1/auth/me", "/"),
        ("https://evil.example", "/"),
    ],
)
def test_safe_redirect(target: str | None, expected: str) -> None:
    assert safe_redirect(target) == expected
