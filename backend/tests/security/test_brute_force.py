"""Guide 12.10: brute-force lockout, rate limits, uniform answers."""

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User
from app.services.accounts import MAX_FAILED_SIGN_INS
from tests.auth_helpers import PASSWORD, login, post, register, register_verified
from tests.conftest import MemoryMailer

EMAIL = "ada@example.org"


async def _clear_rate_limits(app: FastAPI) -> None:
    redis: Redis = app.state.redis
    async for key in redis.scan_iter("rl:*"):
        await redis.delete(key)


async def test_wrong_password_and_unknown_account_look_the_same(
    db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    await register_verified(db_client, mailer, EMAIL)
    wrong = await login(db_client, EMAIL, "not the password at all")
    unknown = await login(db_client, "nobody@example.org", "not the password at all")
    assert wrong.status_code == unknown.status_code == 401
    wrong_body = {k: v for k, v in wrong.json().items() if k != "request_id"}
    unknown_body = {k: v for k, v in unknown.json().items() if k != "request_id"}
    assert wrong_body == unknown_body
    assert wrong.json()["detail"] == "Email or password is incorrect."


async def test_ten_failures_lock_the_account(
    db_app: FastAPI, db_client: AsyncClient, mailer: MemoryMailer, db: AsyncSession
) -> None:
    await register_verified(db_client, mailer, EMAIL)
    for _ in range(MAX_FAILED_SIGN_INS):
        await _clear_rate_limits(db_app)  # isolate the lockout from the per-minute limit
        assert (await login(db_client, EMAIL, "not the password at all")).status_code == 401
    await _clear_rate_limits(db_app)
    locked = await login(db_client, EMAIL)  # the right password no longer works
    assert locked.status_code == 401
    assert locked.json()["code"] == "invalid_credentials"
    assert mailer.sent_to(EMAIL)[-1].subject == "Sign-in to Winnow paused"
    user = await db.scalar(select(User).where(User.email == EMAIL))
    assert user is not None
    assert user.locked_until is not None
    assert user.locked_until - datetime.now(UTC) > timedelta(minutes=14)
    actions = (await db.scalars(select(AuditLog.action).where(AuditLog.user_id == user.id))).all()
    assert "auth.lockout" in actions

    # After fifteen minutes the account opens again.
    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(locked_until=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db.commit()
    assert (await login(db_client, EMAIL)).status_code == 200


async def test_success_resets_the_failure_count(
    db_app: FastAPI, db_client: AsyncClient, mailer: MemoryMailer, db: AsyncSession
) -> None:
    await register_verified(db_client, mailer, EMAIL)
    for _ in range(3):
        await login(db_client, EMAIL, "not the password at all")
    await _clear_rate_limits(db_app)
    await login(db_client, EMAIL)
    assert await db.scalar(select(User.failed_login_count).where(User.email == EMAIL)) == 0


async def test_sign_in_is_rate_limited_per_account_and_ip(db_client: AsyncClient) -> None:
    for _ in range(5):
        assert (await login(db_client, EMAIL, "not the password at all")).status_code == 401
    limited = await login(db_client, EMAIL, "not the password at all")
    assert limited.status_code == 429
    assert limited.json()["code"] == "rate_limited"
    assert 1 <= int(limited.headers["Retry-After"]) <= 60
    # Another account from the same address is still allowed (until the hourly IP cap).
    assert (
        await login(db_client, "someone@example.org", "not the password at all")
    ).status_code == 401


async def test_successful_and_two_step_sign_ins_do_not_count(
    db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    await register_verified(db_client, mailer, EMAIL)
    for _ in range(8):
        assert (await login(db_client, EMAIL)).status_code == 200
    for _ in range(4):
        assert (await login(db_client, EMAIL, "not the password at all")).status_code == 401
    assert (await login(db_client, EMAIL)).status_code == 200  # still under the limit


async def test_registration_is_rate_limited_per_ip(db_client: AsyncClient) -> None:
    for n in range(5):
        assert (await register(db_client, f"user{n}@example.org")).status_code == 202
    limited = await register(db_client, "user5@example.org")
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 60


async def test_password_reset_requests_are_rate_limited(db_client: AsyncClient) -> None:
    for _ in range(5):
        assert (await post(db_client, "/password/forgot", {"email": EMAIL})).status_code == 202
    assert (await post(db_client, "/password/forgot", {"email": EMAIL})).status_code == 429


async def test_lockout_failures_are_counted_atomically(
    db_app: FastAPI, db_client: AsyncClient, mailer: MemoryMailer, db: AsyncSession
) -> None:
    await register_verified(db_client, mailer, EMAIL, PASSWORD)
    await login(db_client, EMAIL, "not the password at all")
    await login(db_client, EMAIL, "not the password at all either")
    assert await db.scalar(select(User.failed_login_count).where(User.email == EMAIL)) == 2
