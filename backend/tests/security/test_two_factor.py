"""TOTP two-factor authentication end to end, including replay and recovery codes."""

import time

import pyotp
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from tests.auth_helpers import AUTH, PASSWORD, enable_two_factor, login, post, signed_in
from tests.conftest import MemoryMailer, make_client

EMAIL = "ada@example.org"


async def test_setup_then_enable(
    db_client: AsyncClient, mailer: MemoryMailer, db: AsyncSession
) -> None:
    await signed_in(db_client, mailer, EMAIL)
    setup = (await post(db_client, "/2fa/setup")).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/Winnow:")
    assert setup["qr_code"].startswith("data:image/svg+xml;base64,")
    wrong = await post(db_client, "/2fa/enable", {"code": "000000"})
    assert wrong.status_code == 401
    assert wrong.json()["code"] == "invalid_totp"
    before = db_client.cookies.get("__Host-winnow_session")
    enabled = await post(db_client, "/2fa/enable", {"code": pyotp.TOTP(setup["secret"]).now()})
    assert enabled.status_code == 200
    assert len(enabled.json()["recovery_codes"]) == 10
    assert db_client.cookies.get("__Host-winnow_session") != before  # privilege change rotates
    me = (await db_client.get(f"{AUTH}/me")).json()
    assert me["totp_enabled"] is True
    assert me["recovery_codes_left"] == 10
    assert mailer.sent_to(EMAIL)[-1].subject == "Two-factor authentication turned on"

    user = await db.scalar(select(User).where(User.email == EMAIL))
    assert user is not None
    assert user.totp_secret_enc is not None
    assert setup["secret"].encode() not in user.totp_secret_enc  # encrypted at rest
    assert all(code not in user.recovery_codes_hash for code in enabled.json()["recovery_codes"])


async def test_sign_in_asks_for_and_checks_the_code(
    db_app: FastAPI, db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    await signed_in(db_client, mailer, EMAIL)
    await enable_two_factor(db_client)
    async with make_client(db_app) as laptop:
        first = await login(laptop, EMAIL)
        assert first.status_code == 401
        assert first.json()["code"] == "totp_required"
        assert (await laptop.get(f"{AUTH}/me")).status_code == 401  # no session yet
        wrong = await login(laptop, EMAIL, totp="123456")
        assert wrong.status_code == 401
        assert wrong.json()["code"] in {"invalid_totp", "rate_limited"}


async def test_a_code_works_only_once(
    db_app: FastAPI, db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    await signed_in(db_client, mailer, EMAIL)
    otp, _ = await enable_two_factor(db_client)
    # The enabling code already used this window; the next window's code is also accepted
    # (clock tolerance) and then can't be replayed.
    code = otp.at(int(time.time()) + 30)
    async with make_client(db_app) as laptop:
        assert (await login(laptop, EMAIL, totp=code)).status_code == 200
    async with make_client(db_app, ip="10.0.0.2") as attacker:
        replay = await login(attacker, EMAIL, totp=code)
        assert replay.status_code == 401
        assert replay.json()["code"] == "invalid_totp"


async def test_recovery_codes_work_once(
    db_app: FastAPI, db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    await signed_in(db_client, mailer, EMAIL)
    _, codes = await enable_two_factor(db_client)
    async with make_client(db_app) as laptop:
        assert (await login(laptop, EMAIL, totp=codes[0].upper())).status_code == 200
        assert (await laptop.get(f"{AUTH}/me")).json()["recovery_codes_left"] == 9
    async with make_client(db_app, ip="10.0.0.3") as again:
        assert (await login(again, EMAIL, totp=codes[0])).status_code == 401


async def test_disable_needs_password_and_code(
    db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    await signed_in(db_client, mailer, EMAIL)
    _, codes = await enable_two_factor(db_client)
    wrong_password = await post(
        db_client, "/2fa/disable", {"password": "not the password", "code": codes[0]}
    )
    assert wrong_password.status_code == 422
    wrong_code = await post(db_client, "/2fa/disable", {"password": PASSWORD, "code": "999999"})
    assert wrong_code.status_code == 401
    disabled = await post(db_client, "/2fa/disable", {"password": PASSWORD, "code": codes[1]})
    assert disabled.status_code == 200
    assert (await db_client.get(f"{AUTH}/me")).json()["totp_enabled"] is False
    assert (
        await post(db_client, "/2fa/disable", {"password": PASSWORD, "code": codes[2]})
    ).status_code == 409


async def test_regenerating_recovery_codes_retires_the_old_ones(
    db_app: FastAPI, db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    await signed_in(db_client, mailer, EMAIL)
    _, old_codes = await enable_two_factor(db_client)
    fresh = await post(db_client, "/2fa/recovery-codes", {"code": old_codes[0]})
    assert fresh.status_code == 200
    new_codes = fresh.json()["recovery_codes"]
    assert set(new_codes).isdisjoint(old_codes)
    async with make_client(db_app) as laptop:
        assert (await login(laptop, EMAIL, totp=old_codes[1])).status_code == 401
        assert (await login(laptop, EMAIL, totp=new_codes[0])).status_code == 200


async def test_setup_twice_or_enable_without_setup(
    db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    await signed_in(db_client, mailer, EMAIL)
    assert (await post(db_client, "/2fa/enable", {"code": "123456"})).status_code == 409
    await enable_two_factor(db_client)
    assert (await post(db_client, "/2fa/setup")).status_code == 409
    assert (await post(db_client, "/2fa/enable", {"code": "123456"})).status_code == 409
