"""The instance administrator's panel (guide 8.18)."""

import json

import pyotp
from fastapi import FastAPI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User
from tests.auth_helpers import enable_two_factor, login
from tests.conftest import MemoryMailer, make_client
from tests.project_helpers import OWNER, REVIEWER, api, create_project, get, person, post
from tests.screening_helpers import add_records

ADMIN_ROUTES = [
    ("GET", "/admin/users"),
    ("GET", "/admin/settings"),
    ("PATCH", "/admin/settings"),
    ("GET", "/admin/health"),
]


async def make_admin(db: AsyncSession, email: str = OWNER) -> None:
    await db.execute(update(User).where(User.email == email).values(is_instance_admin=True))
    await db.commit()


async def test_the_panel_is_hidden_from_everyone_else(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with person(db_app, mailer, REVIEWER, ip="10.8.0.1") as someone:
        for method, path in ADMIN_ROUTES:
            response = await api(someone, method, path, {} if method == "PATCH" else None)
            assert response.status_code == 404, f"{method} {path}"
    async with make_client(db_app, ip="10.8.0.2") as stranger:
        assert (await stranger.get("/api/v1/admin/users")).status_code == 401


async def test_people_are_listed_found_and_disabled(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with (
        person(db_app, mailer, OWNER, ip="10.8.1.1") as admin,
        person(db_app, mailer, REVIEWER, ip="10.8.1.2") as grace,
    ):
        await make_admin(db)
        await create_project(grace)
        page = (await get(admin, "/admin/users?limit=1")).json()
        assert page["total"] == 2
        assert len(page["items"]) == 1
        rest = (await get(admin, f"/admin/users?limit=1&cursor={page['next_cursor']}")).json()
        assert rest["next_cursor"] is None
        found = (await get(admin, "/admin/users?q=grace")).json()["items"]
        assert [(u["email"], u["reviews"], u["disabled"]) for u in found] == [(REVIEWER, 1, False)]
        uid = found[0]["id"]
        me = (await get(admin, "/admin/users?q=ada@example")).json()["items"][0]
        assert me["is_instance_admin"] is True

        # Not yourself: someone has to be left to enable accounts again.
        assert (await post(admin, f"/admin/users/{me['id']}/disable")).status_code == 409
        disabled = await post(admin, f"/admin/users/{uid}/disable")
        assert disabled.json()["disabled"] is True
        # Their sessions ended; the right password is told the account is disabled, and
        # only the right one (a wrong one is a wrong password, as for anyone).
        assert (await grace.get("/api/v1/auth/me")).status_code == 401
        async with make_client(db_app, ip="10.8.1.3") as again:
            refused = await login(again, REVIEWER)
            assert refused.status_code == 403
            assert refused.json()["code"] == "account_disabled"
            assert (await login(again, REVIEWER, "not the password")).status_code == 401

            enabled = await post(admin, f"/admin/users/{uid}/enable")
            assert enabled.json()["disabled"] is False
            assert (await login(again, REVIEWER)).status_code == 200

        actions = set(await db.scalars(select(AuditLog.action)))
        assert {"admin.user_disabled", "admin.user_enabled"} <= actions
        assert (
            await post(admin, "/admin/users/00000000-0000-4000-8000-000000000000/enable")
        ).status_code == 404


async def test_a_lost_authenticator_is_reset_and_sessions_ended(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with (
        person(db_app, mailer, OWNER, ip="10.8.2.1") as admin,
        person(db_app, mailer, REVIEWER, ip="10.8.2.2") as grace,
    ):
        await make_admin(db)
        totp, _ = await enable_two_factor(grace)
        assert isinstance(totp, pyotp.TOTP)
        uid = (await get(admin, "/admin/users?q=grace")).json()["items"][0]["id"]
        reset = await post(admin, f"/admin/users/{uid}/reset-2fa")
        assert reset.status_code == 200, reset.text
        assert reset.json()["two_factor"] is False
        assert (await grace.get("/api/v1/auth/me")).status_code == 401
        assert mailer.sent_to(REVIEWER)[-1].subject == "Two-factor authentication turned off"
        # Nothing to reset twice.
        assert (await post(admin, f"/admin/users/{uid}/reset-2fa")).status_code == 409
        async with make_client(db_app, ip="10.8.2.3") as again:
            assert (await login(again, REVIEWER)).status_code == 200  # password alone

            ended = await post(admin, f"/admin/users/{uid}/sign-out")
            assert ended.json() == {"ended": 1}
            assert (await again.get("/api/v1/auth/me")).status_code == 401


async def test_registration_and_the_unpaywall_email_change_while_running(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with person(db_app, mailer, OWNER, ip="10.8.3.1") as admin:
        await make_admin(db)
        before = (await get(admin, "/admin/settings")).json()
        assert before["registration"] == {"value": "open", "source": "environment"}
        assert "smtp_password" not in json.dumps(before)
        assert set(before) >= {"email_configured", "llm_configured", "virus_scanner", "version"}

        closed = await api(admin, "PATCH", "/admin/settings", {"registration": "closed"})
        assert closed.json()["registration"] == {"value": "closed", "source": "admin"}
        async with make_client(db_app, ip="10.8.3.2") as visitor:
            assert (await visitor.get("/api/v1/auth/options")).json()["registration"] == "closed"
            registered = await api(
                visitor,
                "POST",
                "/auth/register",
                {"name": "Linus", "email": "linus@example.org", "password": "a sturdy passphrase"},
            )
            assert registered.status_code == 403

            back = await api(admin, "PATCH", "/admin/settings", {"registration": "environment"})
            assert back.json()["registration"]["source"] == "environment"
            assert (await visitor.get("/api/v1/auth/options")).json()["registration"] == "open"

        email = await api(admin, "PATCH", "/admin/settings", {"unpaywall_email": "lib@example.org"})
        assert email.json()["unpaywall_email"] == {"value": "lib@example.org", "source": "admin"}
        bad = await api(admin, "PATCH", "/admin/settings", {"unpaywall_email": "not an email"})
        assert bad.status_code == 422
        cleared = await api(admin, "PATCH", "/admin/settings", {"unpaywall_email": ""})
        assert cleared.json()["unpaywall_email"]["source"] == "environment"
        actions = list(
            await db.scalars(
                select(AuditLog.action).where(AuditLog.action == "admin.settings_changed")
            )
        )
        assert len(actions) == 4


async def test_health_reports_queue_worker_disk_and_last_backup(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with (
        person(db_app, mailer, OWNER, ip="10.8.4.1") as admin,
        person(db_app, mailer, REVIEWER, ip="10.8.4.2") as grace,
    ):
        await make_admin(db)
        # A review the admin is not on: its records count all the same, although the
        # admin's requests cannot read them (row-level security).
        theirs = (await create_project(grace))["id"]
        await add_records(db, theirs, 3)
        quiet = (await get(admin, "/admin/health")).json()
        assert quiet["queue"] == {"waiting": 0, "worker_alive": False, "worker_report": {}}
        assert quiet["last_backup"] is None
        assert quiet["database_bytes"] > 0
        assert (quiet["users"], quiet["reviews"], quiet["records"]) == (2, 1, 3)

        redis = db_app.state.redis
        await redis.set(
            "arq:queue:health-check",
            "Sep-25 07:24:16 j_complete=12 j_failed=1 j_retried=0 j_ongoing=2 queued=3",
        )
        await redis.zadd("arq:queue", {"job-a": 1, "job-b": 2})
        await redis.set(
            "winnow:last-backup",
            json.dumps(
                {
                    "at": "2026-09-25T02:00:00+00:00",
                    "file": "winnow-2026-09-25.tar.age",
                    "size_bytes": 1024,
                }
            ),
        )
        busy = (await get(admin, "/admin/health")).json()
        assert busy["queue"]["waiting"] == 2
        assert busy["queue"]["worker_alive"] is True
        assert busy["queue"]["worker_report"] == {
            "j_complete": 12,
            "j_failed": 1,
            "j_retried": 0,
            "j_ongoing": 2,
            "queued": 3,
        }
        assert busy["last_backup"]["file"] == "winnow-2026-09-25.tar.age"
        if busy["disk"] is not None:
            assert busy["disk"]["total_bytes"] >= busy["disk"]["free_bytes"]
        await redis.set("winnow:last-backup", "not json")
        assert (await get(admin, "/admin/health")).json()["last_backup"] is None
