"""Phase 2 acceptance: two people work on one review with the right permissions."""

from fastapi import FastAPI

from app.main import create_app
from tests.auth_helpers import login, register
from tests.conftest import MemoryMailer, make_client, make_settings
from tests.project_helpers import (
    OWNER,
    REVIEWER,
    create_project,
    delete,
    get,
    invite,
    patch,
    person,
    post,
    token_from,
)


async def test_two_people_run_a_review_together(db_app: FastAPI, mailer: MemoryMailer) -> None:
    async with person(db_app, mailer, OWNER, ip="10.2.0.1") as ada:
        project = await create_project(ada, "Shift work and sleep quality")
        pid = project["id"]
        await post(ada, f"/projects/{pid}/criteria", {"kind": "inclusion", "text": "Nurses"})
        created = await invite(ada, pid, REVIEWER, role="reviewer")
        assert created["emailed"] is False  # this instance has no SMTP; share the link

        # The invitation arrives by email, with a link to the invitation page.
        message = mailer.sent_to(REVIEWER)[-1]
        assert "Shift work and sleep quality" in message.body
        assert "Ada Lovelace invited you" in message.body
        token = mailer.token(REVIEWER, "invite")
        assert token == token_from(created["link"])

        async with make_client(db_app, ip="10.2.0.2") as grace:
            # Before signing in, the page can say what the invitation is for.
            preview = (await get(grace, f"/invites/{token}")).json()
            assert preview["project_title"] == "Shift work and sleep quality"
            assert preview["role"] == "reviewer"
            assert preview["state"] == "pending"

            # Grace makes an account, confirms it and accepts.
            assert (await register(grace, REVIEWER, name="Grace Hopper")).status_code == 202
            await post(grace, "/auth/verify-email", {"token": mailer.token(REVIEWER, "verify")})
            await login(grace, REVIEWER)
            accepted = await post(grace, f"/invites/{token}/accept")
            assert accepted.status_code == 200
            assert accepted.json()["project_id"] == pid

            # She sees the review and its criteria, and may not change them.
            joined = (await get(grace, f"/projects/{pid}")).json()
            assert joined["title"] == "Shift work and sleep quality"
            assert joined["membership"]["role"] == "reviewer"
            assert joined["permissions"] == ["view", "screen", "export"]
            assert [c["text"] for c in (await get(grace, f"/projects/{pid}/criteria")).json()] == [
                "Nurses"
            ]
            assert (
                await post(grace, f"/projects/{pid}/criteria", {"kind": "inclusion", "text": "No"})
            ).status_code == 403
            assert (
                await post(grace, f"/projects/{pid}/invites", {"email": "x@y.org"})
            ).status_code == 403

            # Ada promotes her, and now she can run the review too.
            members = (await get(ada, f"/projects/{pid}/members")).json()["items"]
            grace_id = next(m["user"]["id"] for m in members if m["user"]["email"] == REVIEWER)
            promoted = await patch(
                ada,
                f"/projects/{pid}/members/{grace_id}",
                {"role": "admin", "can_resolve_conflicts": True, "stages": ["title_abstract"]},
            )
            assert promoted.status_code == 200
            assert promoted.json()["role"] == "admin"
            assert promoted.json()["stages"] == ["title_abstract"]
            assert (
                await post(
                    grace, f"/projects/{pid}/criteria", {"kind": "exclusion", "text": "Animals"}
                )
            ).status_code == 201
            assert (
                "resolve_conflicts" in (await get(grace, f"/projects/{pid}")).json()["permissions"]
            )
            # Still not hers to delete.
            assert (await delete(grace, f"/projects/{pid}")).status_code == 403

            # Both see the same team of two.
            for client in (ada, grace):
                listed = (await get(client, f"/projects/{pid}/members")).json()["items"]
                assert [m["role"] for m in listed] == ["owner", "admin"]
                assert [m["user"]["name"] for m in listed] == ["Ada Lovelace", "Grace Hopper"]

            # Grace leaves; the review disappears from her dashboard.
            assert (await delete(grace, f"/projects/{pid}/membership")).status_code == 204
            assert (await get(grace, "/projects")).json()["items"] == []
            assert (await get(ada, f"/projects/{pid}")).json()["member_count"] == 1


async def test_registration_can_be_by_invitation_only(
    db_app: FastAPI, mailer: MemoryMailer
) -> None:
    """Guide 8.1 and 16.1: on an invite-only instance the link is the way in."""
    settings = make_settings(
        database_url=db_app.state.settings.database_url,
        redis_url=db_app.state.settings.redis_url,
        registration="invite_only",
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.sessionmaker = db_app.state.sessionmaker
        app.state.mailer = mailer
        async with person(db_app, mailer, OWNER, ip="10.2.1.1") as ada:
            project = await create_project(ada, "Invite only")
            created = await invite(ada, project["id"], REVIEWER)
        async with make_client(app, ip="10.2.1.2") as grace:
            closed = await register(grace, REVIEWER)
            assert closed.status_code == 403
            assert closed.json()["code"] == "registration_closed"

            wrong_address = await post(
                grace,
                "/auth/register",
                {
                    "name": "Grace Hopper",
                    "email": "someone@example.org",
                    "password": "a sturdy passphrase for tests",
                    "invite_token": token_from(created["link"]),
                },
            )
            assert wrong_address.status_code == 403

            welcomed = await post(
                grace,
                "/auth/register",
                {
                    "name": "Grace Hopper",
                    "email": REVIEWER,
                    "password": "a sturdy passphrase for tests",
                    "invite_token": token_from(created["link"]),
                },
            )
            assert welcomed.status_code == 202
            await post(grace, "/auth/verify-email", {"token": mailer.token(REVIEWER, "verify")})
            assert (await login(grace, REVIEWER)).status_code == 200
