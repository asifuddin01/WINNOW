"""Sign in with ORCID against a fake ORCID that signs real RS256 ID tokens.

An iD signs in only to the account whose owner linked it (docs/decisions.md).
"""

import time
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import AsyncClient, Response
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog
from app.security.google import GoogleClient
from app.security.orcid import OrcidClient
from tests.auth_helpers import AUTH, delete, enable_two_factor, post, signed_in
from tests.conftest import MemoryMailer, make_client

CLIENT_ID = "APP-WINNOWTEST0001"
BASE = "https://sandbox.orcid.org"
ORCID = f"{AUTH}/orcid"
IDENTIFIER = "0000-0002-1825-0097"


class FakeOrcid:
    """ORCID's token and key endpoints, holding the signing key and the code it issued."""

    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.subject = IDENTIFIER
        self.nonce = ""
        self.audience = CLIENT_ID
        self.signing_key: Any = self.key

    def remember(self, location: str) -> dict[str, str]:
        query = {k: v[0] for k, v in parse_qs(urlsplit(location).query).items()}
        self.nonce = query["nonce"]
        return query

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/jwks":
            jwk = jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key(), as_dict=True)
            return httpx.Response(200, json={"keys": [{**jwk, "kid": "orcid-1"}]})
        form = parse_qs(request.content.decode())
        if form["code"] != ["Q70Y3A"] or form["client_secret"] != ["test-client-secret"]:
            return httpx.Response(400, json={"error": "invalid_grant"})
        now = int(time.time())
        token = jwt.encode(
            {
                "iss": BASE,
                "aud": self.audience,
                "sub": self.subject,
                "iat": now,
                "exp": now + 300,
                "nonce": self.nonce,
                "given_name": "Grace",
                "family_name": "Hopper",
            },
            self.signing_key,
            algorithm="RS256",
            headers={"kid": "orcid-1"},
        )
        return httpx.Response(200, json={"id_token": token, "orcid": self.subject})


@pytest.fixture
async def orcid(db_app: FastAPI) -> AsyncIterator[FakeOrcid]:
    fake = FakeOrcid()
    settings = db_app.state.settings
    settings.orcid_client_id = CLIENT_ID
    settings.orcid_client_secret = SecretStr("test-client-secret")
    settings.orcid_base_url = BASE
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake.handle))
    db_app.state.orcid = OrcidClient(http, CLIENT_ID, "test-client-secret", BASE)
    yield fake
    await http.aclose()


async def callback(client: AsyncClient, state: str, **extra: str) -> Response:
    return await client.get(f"{ORCID}/callback", params={"state": state, "code": "Q70Y3A", **extra})


async def sign_in_with_orcid(
    client: AsyncClient, orcid: FakeOrcid, redirect: str | None = None
) -> Response:
    response = await client.get(
        f"{ORCID}/start", params={"redirect": redirect} if redirect else None
    )
    assert response.status_code == 303
    return await callback(client, orcid.remember(response.headers["location"])["state"])


async def link(client: AsyncClient, orcid: FakeOrcid) -> Response:
    started = await post(client, "/orcid/link", {})
    assert started.status_code == 200
    return await callback(client, orcid.remember(started.json()["url"])["state"])


async def test_start_sends_the_browser_to_orcid(db_client: AsyncClient, orcid: FakeOrcid) -> None:
    response = await db_client.get(f"{ORCID}/start")
    location = urlsplit(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == f"{BASE}/oauth/authorize"
    query = parse_qs(location.query)
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == ["https://testserver/api/v1/auth/orcid/callback"]
    assert query["scope"] == ["openid"]
    assert len(query["state"][0]) >= 40
    assert len(query["nonce"][0]) >= 30
    cookie = next(
        h for h in response.headers.get_list("set-cookie") if h.startswith("__Host-winnow_oauth=")
    )
    assert "samesite=lax" in cookie.lower()


async def test_an_id_nobody_linked_signs_in_to_nothing(
    db_client: AsyncClient, orcid: FakeOrcid, db: AsyncSession
) -> None:
    response = await sign_in_with_orcid(db_client, orcid)
    assert response.headers["location"] == "/login?error=orcid_not_linked"
    assert (await db_client.get(f"{AUTH}/me")).status_code == 401


async def test_link_then_sign_in(
    db_app: FastAPI,
    db_client: AsyncClient,
    orcid: FakeOrcid,
    mailer: MemoryMailer,
    db: AsyncSession,
) -> None:
    await signed_in(db_client, mailer, "grace@example.org")
    assert (await db_client.get(f"{AUTH}/me")).json()["orcid"] is None
    response = await link(db_client, orcid)
    assert response.headers["location"] == "/account?orcid=linked"
    assert (await db_client.get(f"{AUTH}/me")).json()["orcid"] == IDENTIFIER
    # Linking the same iD again changes nothing.
    assert (await link(db_client, orcid)).headers["location"] == "/account?orcid=linked"
    assert "auth.identity.linked" in set((await db.scalars(select(AuditLog.action))).all())

    async with make_client(db_app) as laptop:
        response = await sign_in_with_orcid(laptop, orcid, "/account")
        assert response.headers["location"] == "/account"
        me = (await laptop.get(f"{AUTH}/me")).json()
        assert (me["email"], me["orcid"]) == ("grace@example.org", IDENTIFIER)


async def test_an_id_links_to_one_account_only(
    db_app: FastAPI, db_client: AsyncClient, orcid: FakeOrcid, mailer: MemoryMailer
) -> None:
    await signed_in(db_client, mailer, "grace@example.org")
    await link(db_client, orcid)
    async with make_client(db_app) as other:
        await signed_in(other, mailer, "ada@example.org")
        response = await link(other, orcid)
        assert response.headers["location"] == "/account?orcid=orcid_taken"
        assert (await other.get(f"{AUTH}/me")).json()["orcid"] is None


async def test_a_link_finishes_only_in_the_session_that_started_it(
    db_client: AsyncClient, orcid: FakeOrcid, mailer: MemoryMailer
) -> None:
    """On a shared computer, whoever signs in next must not put their iD on the account."""
    await signed_in(db_client, mailer, "grace@example.org")
    started = await post(db_client, "/orcid/link", {})
    state = orcid.remember(started.json()["url"])["state"]
    await post(db_client, "/logout", {})
    await signed_in(db_client, mailer, "ada@example.org")
    response = await callback(db_client, state)
    assert response.headers["location"] == "/login?error=orcid_state"
    assert (await db_client.get(f"{AUTH}/me")).json()["orcid"] is None


async def test_linking_needs_a_session(db_client: AsyncClient, orcid: FakeOrcid) -> None:
    assert (await post(db_client, "/orcid/link", {})).status_code == 401


@pytest.mark.parametrize(
    ("tamper", "expected"),
    [
        (lambda o: setattr(o, "audience", "someone-elses-app"), "orcid_failed"),
        (lambda o: setattr(o, "nonce", "a-nonce-from-another-sign-in"), "orcid_failed"),
        (lambda o: setattr(o, "subject", "not-an-orcid-id"), "orcid_failed"),
        (
            lambda o: setattr(
                o, "signing_key", rsa.generate_private_key(public_exponent=65537, key_size=2048)
            ),
            "orcid_failed",
        ),
    ],
    ids=["wrong-audience", "replayed-nonce", "malformed-id", "forged-signature"],
)
async def test_untrustworthy_tokens_are_refused(
    db_client: AsyncClient, orcid: FakeOrcid, mailer: MemoryMailer, tamper: Any, expected: str
) -> None:
    await signed_in(db_client, mailer, "grace@example.org")
    started = await post(db_client, "/orcid/link", {})
    state = orcid.remember(started.json()["url"])["state"]
    tamper(orcid)
    response = await callback(db_client, state)
    assert response.headers["location"] == f"/account?orcid={expected}"
    assert (await db_client.get(f"{AUTH}/me")).json()["orcid"] is None


async def test_cancelling_at_orcid(
    db_client: AsyncClient, orcid: FakeOrcid, mailer: MemoryMailer
) -> None:
    start = await db_client.get(f"{ORCID}/start")
    state = orcid.remember(start.headers["location"])["state"]
    response = await db_client.get(
        f"{ORCID}/callback", params={"state": state, "error": "access_denied"}
    )
    assert response.headers["location"] == "/login?error=orcid_cancelled"
    start = await db_client.get(f"{ORCID}/start")
    no_code = await db_client.get(
        f"{ORCID}/callback", params={"state": orcid.remember(start.headers["location"])["state"]}
    )
    assert no_code.headers["location"] == "/login?error=orcid_failed"
    # A state not bound to this browser, or used already.
    assert (await callback(db_client, state)).headers["location"] == "/login?error=orcid_state"


async def test_two_factor_still_applies(
    db_app: FastAPI, db_client: AsyncClient, orcid: FakeOrcid, mailer: MemoryMailer
) -> None:
    await signed_in(db_client, mailer, "grace@example.org")
    await link(db_client, orcid)
    otp, _ = await enable_two_factor(db_client)
    async with make_client(db_app) as laptop:
        response = await sign_in_with_orcid(laptop, orcid, "/account")
        assert response.headers["location"] == "/login?step=orcid-2fa"
        assert (await laptop.get(f"{AUTH}/me")).status_code == 401
        # Started with ORCID, so it finishes there, not at Google's endpoint.
        db_app.state.settings.google_client_id = "google-client"
        db_app.state.settings.google_client_secret = SecretStr("google-secret")
        db_app.state.google = GoogleClient(httpx.AsyncClient(), "google-client", "google-secret")
        elsewhere = await post(laptop, "/google/two-factor", {"code": otp.now()})
        assert elsewhere.json()["code"] == "google_pending_expired"
        done = await post(laptop, "/orcid/two-factor", {"code": otp.at(int(time.time()) + 30)})
        assert done.status_code == 200
        assert done.json()["redirect"] == "/account"
        again = await post(laptop, "/orcid/two-factor", {"code": otp.now()})
        assert again.json()["code"] == "orcid_pending_expired"


async def test_unlinking(
    db_app: FastAPI, db_client: AsyncClient, orcid: FakeOrcid, mailer: MemoryMailer
) -> None:
    await signed_in(db_client, mailer, "grace@example.org")
    await link(db_client, orcid)
    assert (await delete(db_client, "/orcid")).status_code == 204
    assert (await db_client.get(f"{AUTH}/me")).json()["orcid"] is None
    async with make_client(db_app) as laptop:
        response = await sign_in_with_orcid(laptop, orcid)
        assert response.headers["location"] == "/login?error=orcid_not_linked"


async def test_orcid_is_off_until_configured(db_client: AsyncClient, mailer: MemoryMailer) -> None:
    assert (await db_client.get(f"{AUTH}/options")).json()["orcid_enabled"] is False
    assert (await db_client.get(f"{ORCID}/start")).status_code == 404
    assert (await db_client.get(f"{ORCID}/callback", params={"state": "x"})).status_code == 404
    await signed_in(db_client, mailer, "grace@example.org")
    assert (await post(db_client, "/orcid/link", {})).status_code == 404
    # Unlinking still works, for an iD linked while the instance offered ORCID.
    assert (await delete(db_client, "/orcid")).status_code == 204
