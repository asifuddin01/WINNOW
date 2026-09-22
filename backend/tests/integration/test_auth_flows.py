"""Registration, verification, sign-in and passwords through the HTTP API."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, EmailToken, User
from tests.auth_helpers import (
    AUTH,
    PASSWORD,
    csrf,
    login,
    post,
    register,
    register_verified,
    signed_in,
)
from tests.conftest import MemoryMailer, make_client

EMAIL = "ada@example.org"


async def test_options_describe_the_instance(db_client: AsyncClient) -> None:
    response = await db_client.get(f"{AUTH}/options")
    assert response.json() == {
        "registration": "open",
        "single_user": False,
        "needs_setup": False,
        "email_enabled": False,
        "google_enabled": False,
    }


async def test_register_sends_a_verification_link(
    db_client: AsyncClient, mailer: MemoryMailer, db: AsyncSession
) -> None:
    response = await register(db_client, EMAIL)
    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    user = await db.scalar(select(User).where(User.email == EMAIL))
    assert user is not None
    assert not user.email_verified
    assert user.password_hash.startswith("$argon2id$")
    [email] = mailer.sent_to(EMAIL)
    assert "https://testserver/verify/" in email.body
    assert (
        await db.scalar(select(AuditLog.action).where(AuditLog.user_id == user.id))
        == "auth.register"
    )


async def test_register_does_not_reveal_existing_accounts(
    db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    first = await register(db_client, EMAIL)
    second = await register(db_client, EMAIL.upper(), name="Someone Else")
    assert second.status_code == first.status_code == 202
    assert second.json() == first.json()
    assert [e.subject for e in mailer.sent_to(EMAIL)] == [
        "Confirm your email for Winnow",
        "You already have a Winnow account",
    ]


@pytest.mark.parametrize(
    ("password", "reason"),
    [("short pass", "at least 12"), ("ada@example.org", "not your email"), ("x" * 257, None)],
)
async def test_weak_passwords_are_refused(
    db_client: AsyncClient, password: str, reason: str | None
) -> None:
    response = await register(db_client, EMAIL, password)
    assert response.status_code == 422
    if reason:
        assert response.json()["code"] == "weak_password"
        assert reason in response.json()["detail"]


async def test_breached_passwords_are_refused(
    db_app: FastAPI, db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_app.state.settings.password_breach_check = True

    async def breached(password: str, http: object) -> bool:
        return True

    monkeypatch.setattr("app.services.accounts.is_breached", breached)
    response = await register(db_client, EMAIL)
    assert response.status_code == 422
    assert "data breach" in response.json()["detail"]


@pytest.mark.parametrize(("mode", "phrase"), [("closed", "closed"), ("invite_only", "invitation")])
async def test_registration_can_be_closed(
    db_app: FastAPI, db_client: AsyncClient, mode: str, phrase: str
) -> None:
    db_app.state.settings.registration = mode
    response = await register(db_client, EMAIL)
    assert response.status_code == 403
    assert response.json()["code"] == "registration_closed"
    assert phrase in response.json()["detail"]


async def test_verification_links_work_once(
    db_client: AsyncClient, mailer: MemoryMailer, db: AsyncSession
) -> None:
    await register(db_client, EMAIL)
    token = mailer.token(EMAIL, "verify")
    first = await post(db_client, "/verify-email", {"token": token})
    assert first.status_code == 200
    assert first.json()["email_verified"] is True
    again = await post(db_client, "/verify-email", {"token": token})
    assert again.status_code == 400
    assert again.json()["code"] == "invalid_token"


async def test_expired_verification_links_fail(
    db_client: AsyncClient, mailer: MemoryMailer, db: AsyncSession
) -> None:
    await register(db_client, EMAIL)
    token = mailer.token(EMAIL, "verify")
    await db.execute(update(EmailToken).values(expires_at=EmailToken.created_at))
    await db.commit()
    response = await post(db_client, "/verify-email", {"token": token})
    assert response.status_code == 400


async def test_sign_in_and_me(db_client: AsyncClient, mailer: MemoryMailer) -> None:
    await register_verified(db_client, mailer, EMAIL)
    response = await login(db_client, EMAIL)
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == EMAIL
    assert body["user"]["email_verified"] is True
    assert body["csrf_token"]
    me = await db_client.get(f"{AUTH}/me")
    assert me.status_code == 200
    assert me.json()["name"] == "Ada Lovelace"


async def test_unverified_users_can_sign_in_and_resend(
    db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    await register(db_client, EMAIL)
    response = await login(db_client, EMAIL)
    assert response.status_code == 200
    assert response.json()["user"]["email_verified"] is False
    resend = await post(db_client, "/verify-email/resend", token=response.json()["csrf_token"])
    assert resend.status_code == 202
    assert len(mailer.sent_to(EMAIL)) == 2


async def test_logout_ends_the_session(db_client: AsyncClient, mailer: MemoryMailer) -> None:
    token = await signed_in(db_client, mailer)
    response = await post(db_client, "/logout", token=token)
    assert response.status_code == 204
    assert (await db_client.get(f"{AUTH}/me")).status_code == 401
    # Logging out twice is harmless.
    assert (await post(db_client, "/logout")).status_code == 204


async def test_password_reset(
    db_app: FastAPI, db_client: AsyncClient, mailer: MemoryMailer, db: AsyncSession
) -> None:
    await signed_in(db_client, mailer, EMAIL)
    unknown = await post(db_client, "/password/forgot", {"email": "nobody@example.org"})
    known = await post(db_client, "/password/forgot", {"email": EMAIL})
    assert unknown.status_code == known.status_code == 202
    assert unknown.json() == known.json()
    assert mailer.sent_to("nobody@example.org") == []

    token = mailer.token(EMAIL, "reset")
    async with make_client(db_app) as other_browser:
        response = await post(
            other_browser, "/password/reset", {"token": token, "password": "a brand new passphrase"}
        )
    assert response.status_code == 204
    assert (await db_client.get(f"{AUTH}/me")).status_code == 401  # every session ended
    assert (await login(db_client, EMAIL)).status_code == 401
    assert (await login(db_client, EMAIL, "a brand new passphrase")).status_code == 200
    reused = await post(
        db_client, "/password/reset", {"token": token, "password": "yet another passphrase"}
    )
    assert reused.status_code == 400
    assert mailer.sent_to(EMAIL)[-1].subject == "Your Winnow password was changed"


async def test_a_new_reset_link_replaces_the_old_one(
    db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    await register_verified(db_client, mailer, EMAIL)
    await post(db_client, "/password/forgot", {"email": EMAIL})
    old = mailer.token(EMAIL, "reset")
    await post(db_client, "/password/forgot", {"email": EMAIL})
    response = await post(
        db_client, "/password/reset", {"token": old, "password": "a brand new passphrase"}
    )
    assert response.status_code == 400


async def test_weak_reset_password_keeps_the_link_usable(
    db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    await register_verified(db_client, mailer, EMAIL)
    await post(db_client, "/password/forgot", {"email": EMAIL})
    token = mailer.token(EMAIL, "reset")
    assert (
        await post(db_client, "/password/reset", {"token": token, "password": "short"})
    ).status_code == 422
    assert (
        await post(
            db_client, "/password/reset", {"token": token, "password": "a brand new passphrase"}
        )
    ).status_code == 204


async def test_change_password(
    db_app: FastAPI, db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    token = await signed_in(db_client, mailer, EMAIL)
    async with make_client(db_app) as laptop:
        assert (await login(laptop, EMAIL)).status_code == 200
        wrong = await post(
            db_client,
            "/password/change",
            {"current_password": "not it at all", "new_password": "a brand new passphrase"},
            token,
        )
        assert wrong.status_code == 422
        assert wrong.json()["code"] == "incorrect_password"
        changed = await post(
            db_client,
            "/password/change",
            {"current_password": PASSWORD, "new_password": "a brand new passphrase"},
            token,
        )
        assert changed.status_code == 200
        assert (await laptop.get(f"{AUTH}/me")).status_code == 401  # other devices signed out
    assert (await db_client.get(f"{AUTH}/me")).status_code == 200  # this one continues
    # The session was rotated, so the old CSRF token no longer matches it.
    assert (await post(db_client, "/logout", token=token)).status_code == 403
    assert (await post(db_client, "/logout", token=changed.json()["csrf_token"])).status_code == 204


async def test_single_user_setup(db_app: FastAPI, db_client: AsyncClient, db: AsyncSession) -> None:
    db_app.state.settings.winnow_single_user = True
    options = (await db_client.get(f"{AUTH}/options")).json()
    assert options["single_user"] is True
    assert options["needs_setup"] is True
    body = {"name": "Ada Lovelace", "email": EMAIL, "password": PASSWORD}
    created = await post(db_client, "/setup", body)
    assert created.status_code == 201
    assert created.json()["user"]["is_instance_admin"] is True
    assert created.json()["user"]["email_verified"] is True
    assert (await db_client.get(f"{AUTH}/me")).status_code == 200
    again = await post(db_client, "/setup", {**body, "email": "eve@example.org"})
    assert again.status_code == 403
    assert (await register(db_client, "eve@example.org")).status_code == 403
    assert (await db_client.get(f"{AUTH}/options")).json()["needs_setup"] is False


async def test_setup_is_hidden_outside_single_user_mode(db_client: AsyncClient) -> None:
    response = await post(db_client, "/setup", {"name": "A", "email": EMAIL, "password": PASSWORD})
    assert response.status_code == 404


async def test_csrf_token_changes_with_the_session(
    db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    anonymous = await csrf(db_client)
    signed = await signed_in(db_client, mailer)
    assert anonymous != signed
    assert await csrf(db_client) == signed
