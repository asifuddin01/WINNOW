"""Guide 12.8 and 12.7: the audit log is append-only; logs never carry secrets."""

import logging

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog
from app.security.sessions import SESSION_COOKIE
from tests.auth_helpers import AUTH, PASSWORD, csrf, login, post, register_verified
from tests.conftest import MemoryMailer

EMAIL = "ada@example.org"


async def test_audit_rows_cannot_be_changed_or_deleted(
    db_client: AsyncClient, mailer: MemoryMailer, db: AsyncSession
) -> None:
    await register_verified(db_client, mailer, EMAIL)
    assert await db.scalar(select(AuditLog.id).limit(1)) is not None
    for statement in (update(AuditLog).values(action="tampered"), delete(AuditLog)):
        with pytest.raises(DBAPIError, match="append-only"):
            async with db.begin_nested():
                await db.execute(statement)


async def test_auth_events_are_audited_with_ip_and_agent(
    db_client: AsyncClient, mailer: MemoryMailer, db: AsyncSession
) -> None:
    await register_verified(db_client, mailer, EMAIL)
    await login(db_client, EMAIL, "not the password at all")
    await login(db_client, EMAIL)
    rows = (await db.scalars(select(AuditLog).order_by(AuditLog.id))).all()
    actions = [row.action for row in rows]
    assert actions[:4] == [
        "auth.register",
        "auth.email_verified",
        "auth.login.failure",
        "auth.login.success",
    ]
    assert str(rows[-1].ip) == "127.0.0.1"
    assert rows[-1].user_agent is not None


async def test_secrets_never_reach_the_logs(
    db_client: AsyncClient, mailer: MemoryMailer, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    await register_verified(db_client, mailer, EMAIL)
    await login(db_client, EMAIL)
    await post(db_client, "/password/forgot", {"email": EMAIL})
    reset_token = mailer.token(EMAIL, "reset")
    await post(
        db_client, "/password/reset", {"token": reset_token, "password": "a brand new passphrase"}
    )
    session_id = db_client.cookies.get(SESSION_COOKIE) or "none"
    csrf_token = await csrf(db_client)
    await db_client.get(f"{AUTH}/me")
    text = caplog.text + " ".join(str(record.msg) for record in caplog.records)
    for secret in (PASSWORD, "a brand new passphrase", reset_token, session_id, csrf_token):
        assert secret not in text
