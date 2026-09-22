"""Guide 12.10: session fixation, CSRF, and every non-public route requiring sign-in."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from redis.asyncio import Redis

from app.security.sessions import SESSION_COOKIE, session_key
from tests.auth_helpers import (
    AUTH,
    csrf,
    delete,
    login,
    post,
    register_verified,
    session_cookie,
    session_id,
    signed_in,
)
from tests.conftest import MemoryMailer, make_client

EMAIL = "ada@example.org"
# Routes anyone may call. Everything else under /api/v1 must answer 401 when signed out.
PUBLIC_ROUTES = {
    ("GET", "/api/v1/healthz"),
    ("GET", "/api/v1/readyz"),
    ("GET", "/api/v1/auth/options"),
    ("GET", "/api/v1/auth/csrf"),
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/setup"),
    ("POST", "/api/v1/auth/verify-email"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/password/forgot"),
    ("POST", "/api/v1/auth/password/reset"),
}


async def test_session_cookie_is_host_only_httponly_secure_lax(
    db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    await register_verified(db_client, mailer, EMAIL)
    cookie = session_cookie(await login(db_client, EMAIL))
    assert cookie is not None
    attributes = {part.strip().split("=")[0].lower() for part in cookie.split(";")}
    assert {"httponly", "secure", "path", "max-age"} <= attributes
    assert "samesite=lax" in cookie.lower()
    assert "path=/" in cookie.lower()
    assert "domain" not in attributes


async def test_session_id_changes_on_sign_in(
    db_app: FastAPI, db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    await register_verified(db_client, mailer, EMAIL)
    first = session_id(await login(db_client, EMAIL))
    second = session_id(await login(db_client, EMAIL))
    assert first != second
    async with make_client(db_app) as attacker:
        attacker.cookies.set(SESSION_COOKIE, first)
        assert (await attacker.get(f"{AUTH}/me")).status_code == 401  # the old id is dead
        attacker.cookies.set(SESSION_COOKIE, second)
        assert (await attacker.get(f"{AUTH}/me")).status_code == 200


async def test_a_planted_session_id_is_never_adopted(
    db_app: FastAPI, db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    """Session fixation: an attacker sets the victim's cookie to a value they know; signing in
    must issue a fresh id rather than bless the planted one."""
    await register_verified(db_client, mailer, EMAIL)
    async with make_client(db_app) as victim:
        victim.cookies.set(SESSION_COOKIE, "attacker-chosen-session-id")
        issued = session_id(await login(victim, EMAIL))
    assert issued != "attacker-chosen-session-id"
    async with make_client(db_app) as attacker:
        attacker.cookies.set(SESSION_COOKIE, "attacker-chosen-session-id")
        assert (await attacker.get(f"{AUTH}/me")).status_code == 401


async def test_sessions_expire_after_the_absolute_lifetime(
    db_app: FastAPI, db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    await signed_in(db_client, mailer)
    redis: Redis = db_app.state.redis
    key = f"sess:{session_key(db_client.cookies.get(SESSION_COOKIE) or '')}"
    long_ago = datetime.now(UTC) - timedelta(days=31)
    await redis.hset(  # type: ignore[misc]
        key, mapping={"created_at": long_ago.isoformat(), "last_seen_at": long_ago.isoformat()}
    )
    assert (await db_client.get(f"{AUTH}/me")).status_code == 401
    assert not await redis.exists(key)


async def test_idle_timeout_is_the_redis_ttl(
    db_app: FastAPI, db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    await signed_in(db_client, mailer)
    redis: Redis = db_app.state.redis
    ttl = await redis.ttl(f"sess:{session_key(db_client.cookies.get(SESSION_COOKIE) or '')}")
    assert 6 * 86400 < ttl <= 7 * 86400


async def test_redis_never_holds_the_cookie_value(
    db_app: FastAPI, db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    await signed_in(db_client, mailer)
    raw = db_client.cookies.get(SESSION_COOKIE) or ""
    redis: Redis = db_app.state.redis
    keys = [key async for key in redis.scan_iter("*")]
    assert all(raw not in key for key in keys)


async def test_logout_everywhere(
    db_app: FastAPI, db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    token = await signed_in(db_client, mailer, EMAIL)
    async with make_client(db_app) as phone:
        assert (await login(phone, EMAIL)).status_code == 200
        assert (await post(db_client, "/logout-all", token=token)).status_code == 204
        assert (await phone.get(f"{AUTH}/me")).status_code == 401
    assert (await db_client.get(f"{AUTH}/me")).status_code == 401


async def test_list_and_revoke_sessions(
    db_app: FastAPI, db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    await signed_in(db_client, mailer, EMAIL)
    async with make_client(db_app, ip="10.0.0.9") as phone:
        await login(phone, EMAIL)
        sessions = (await db_client.get(f"{AUTH}/sessions")).json()
        assert len(sessions) == 2
        assert sum(s["current"] for s in sessions) == 1
        other = next(s for s in sessions if not s["current"])
        assert other["ip"] == "10.0.0.9"
        assert (await delete(db_client, f"/sessions/{other['id']}")).status_code == 204
        assert (await phone.get(f"{AUTH}/me")).status_code == 401
    assert (await delete(db_client, "/sessions/not-a-session")).status_code == 404


async def test_sessions_of_other_users_cannot_be_revoked(
    db_app: FastAPI, db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    await signed_in(db_client, mailer, EMAIL)
    async with make_client(db_app) as eve:
        await signed_in(eve, mailer, "eve@example.org")
        eves_session = (await eve.get(f"{AUTH}/sessions")).json()[0]["id"]
    assert (await delete(db_client, f"/sessions/{eves_session}")).status_code == 404


async def test_writes_without_a_csrf_token_are_refused(db_client: AsyncClient) -> None:
    response = await db_client.post(
        f"{AUTH}/login", json={"email": EMAIL, "password": "whatever-it-is"}
    )
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_invalid"


async def test_csrf_token_from_another_browser_is_refused(
    db_app: FastAPI, db_client: AsyncClient
) -> None:
    async with make_client(db_app) as attacker:
        stolen = await csrf(attacker)
    await csrf(db_client)
    response = await post(db_client, "/logout", token=stolen)
    assert response.status_code == 403


@pytest.mark.parametrize("origin", ["https://evil.example", "http://testserver", "null"])
async def test_writes_from_other_origins_are_refused(db_client: AsyncClient, origin: str) -> None:
    token = await csrf(db_client)
    response = await db_client.post(
        f"{AUTH}/logout", headers={"X-CSRF-Token": token, "Origin": origin}
    )
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_origin"


async def test_referer_stands_in_for_a_missing_origin(db_app: FastAPI) -> None:
    async with make_client(db_app) as client:
        token = await csrf(client)
        del client.headers["Origin"]
        missing = await client.post(f"{AUTH}/logout", headers={"X-CSRF-Token": token})
        assert missing.status_code == 403
        with_referer = await client.post(
            f"{AUTH}/logout",
            headers={"X-CSRF-Token": token, "Referer": "https://testserver/account"},
        )
        assert with_referer.status_code == 204


async def test_every_private_route_requires_sign_in(
    db_app: FastAPI, db_client: AsyncClient
) -> None:
    """Walks every operation in the OpenAPI schema, as guide 7 asks, so new routes are
    covered the day they are added."""
    token = await csrf(db_client)
    checked = 0
    for path, operations in db_app.openapi()["paths"].items():
        for method in operations:
            if (method.upper(), path) in PUBLIC_ROUTES:
                continue
            concrete = re.sub(r"\{[^}]+\}", "abc", path)
            response = await db_client.request(
                method.upper(), concrete, headers={"X-CSRF-Token": token}, json={}
            )
            assert response.status_code == 401, (
                f"{method.upper()} {path} answered {response.status_code}"
            )
            checked += 1
    assert checked >= 10
