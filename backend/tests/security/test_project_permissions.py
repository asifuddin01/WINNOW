"""Guide 7 and 12.10: what each role may do, and what outsiders may learn.

The first test is the one the guide asks for by name: it walks every project route in the
OpenAPI schema, so a route added in a later phase is covered the day it appears.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, ProjectInvite, ProjectMember
from tests.auth_helpers import login, register
from tests.conftest import MemoryMailer, make_client
from tests.project_helpers import (
    OWNER,
    REVIEWER,
    add_member,
    api,
    create_project,
    delete,
    get,
    invite,
    patch,
    person,
    post,
    token_from,
)

STRANGER = "mallory@example.org"
# Writes a viewer may make: their own preferences, leaving, and copying the setup into a
# review of their own. Everything else in the project is read-only for them.
VIEWER_WRITES = {
    ("PATCH", "/api/v1/projects/{pid}/membership"),
    ("DELETE", "/api/v1/projects/{pid}/membership"),
    ("POST", "/api/v1/projects/{pid}/duplicate-setup"),
}
# And the ones a reviewer adds: their own screening work (guide 7, "Screen / decide").
REVIEWER_WRITES = VIEWER_WRITES | {
    ("PUT", "/api/v1/projects/{pid}/records/{rid}/decision"),
    ("DELETE", "/api/v1/projects/{pid}/records/{rid}/decision"),
    ("PUT", "/api/v1/projects/{pid}/records/{rid}/labels"),
    ("POST", "/api/v1/projects/{pid}/records/{rid}/notes"),
    ("DELETE", "/api/v1/projects/{pid}/notes/{nid}"),
    # Anyone who screens may ask for the order to catch up with their decisions.
    ("POST", "/api/v1/projects/{pid}/ranking/train"),
    # Asking the AI provider about a record (guide 8.11) is advice, not a decision.
    ("POST", "/api/v1/projects/{pid}/records/{rid}/llm-suggest"),
}


def project_operations(app: FastAPI) -> list[tuple[str, str]]:
    return [
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if "{pid}" in path
    ]


def concrete(path: str, project_id: str) -> str:
    """The path with a real project id and a made-up id for anything else."""
    filled = path.replace("{pid}", project_id)
    while "{" in filled:
        start = filled.index("{")
        end = filled.index("}", start)
        filled = filled[:start] + str(uuid.uuid4()) + filled[end + 1 :]
    return filled


def body_for(method: str) -> dict[str, object] | None:
    return None if method in {"GET", "DELETE"} else {}


async def test_every_project_route_answers_404_for_a_non_member(
    db_app: FastAPI, mailer: MemoryMailer
) -> None:
    async with person(db_app, mailer, OWNER, ip="10.0.0.1") as owner:
        project = await create_project(owner)
    async with person(db_app, mailer, STRANGER, ip="10.0.0.2") as stranger:
        missing = await get(stranger, f"/projects/{uuid.uuid4()}")
        assert missing.status_code == 404
        checked = 0
        for method, path in project_operations(db_app):
            response = await api(
                stranger, method, concrete(path, project["id"])[len("/api/v1") :], body_for(method)
            )
            assert response.status_code == 404, f"{method} {path} answered {response.status_code}"
            # Word for word what a project that does not exist answers, so a stranger
            # cannot tell the difference.
            assert response.json()["detail"] == missing.json()["detail"]
            assert response.json()["code"] == "not_found"
            checked += 1
        assert checked >= 30, "every project route must be covered"


async def test_a_malformed_project_id_is_not_found_rather_than_invalid(
    db_app: FastAPI, mailer: MemoryMailer
) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        assert (await get(owner, "/projects/not-a-uuid")).status_code == 404


async def test_a_deleted_project_is_gone_for_everyone(
    db_app: FastAPI, mailer: MemoryMailer
) -> None:
    async with (
        person(db_app, mailer, OWNER, ip="10.0.1.1") as owner,
        person(db_app, mailer, REVIEWER, ip="10.0.1.2") as reviewer,
    ):
        project = await create_project(owner)
        await add_member(owner, reviewer, project["id"], REVIEWER)
        assert (await delete(owner, f"/projects/{project['id']}")).status_code == 204
        for client in (owner, reviewer):
            assert (await get(client, f"/projects/{project['id']}")).status_code == 404
            assert (await get(client, "/projects")).json()["items"] == []


@pytest.mark.parametrize("role", ["viewer", "reviewer"])
async def test_members_below_admin_cannot_write(
    db_app: FastAPI, mailer: MemoryMailer, role: str
) -> None:
    """Guide 7: only owners and admins change the review; guide 12.10 asks for the
    viewer case explicitly."""
    async with (
        person(db_app, mailer, OWNER, ip="10.0.2.1") as owner,
        person(db_app, mailer, REVIEWER, ip="10.0.2.2") as member,
    ):
        project = await create_project(owner)
        await add_member(owner, member, project["id"], REVIEWER, role=role)
        allowed = REVIEWER_WRITES if role == "reviewer" else VIEWER_WRITES
        for method, path in project_operations(db_app):
            if method == "GET" or (method, path) in allowed:
                continue
            response = await api(
                member, method, concrete(path, project["id"])[len("/api/v1") :], body_for(method)
            )
            assert response.status_code == 403, f"{method} {path} answered {response.status_code}"
            assert response.json()["code"] == "forbidden"


async def test_a_viewer_can_read_and_keep_their_own_preferences(
    db_app: FastAPI, mailer: MemoryMailer
) -> None:
    async with (
        person(db_app, mailer, OWNER, ip="10.0.3.1") as owner,
        person(db_app, mailer, REVIEWER, ip="10.0.3.2") as viewer,
    ):
        project = await create_project(owner)
        await add_member(owner, viewer, project["id"], REVIEWER, role="viewer")
        detail = await get(viewer, f"/projects/{project['id']}")
        assert detail.status_code == 200
        assert detail.json()["permissions"] == ["view", "export"]
        # A viewer sees the team but not their email addresses (guide 12.7).
        members = await get(viewer, f"/projects/{project['id']}/members")
        assert [m["user"]["email"] for m in members.json()["items"]] == [None, None]
        assert (await get(viewer, f"/projects/{project['id']}/criteria")).status_code == 200
        preferences = await patch(
            viewer, f"/projects/{project['id']}/membership", {"keep_blind": False}
        )
        assert preferences.status_code == 200
        assert preferences.json()["keep_blind"] is False
        assert (await delete(viewer, f"/projects/{project['id']}/membership")).status_code == 204
        assert (await get(viewer, f"/projects/{project['id']}")).status_code == 404


async def test_only_the_owner_deletes_or_transfers(db_app: FastAPI, mailer: MemoryMailer) -> None:
    async with (
        person(db_app, mailer, OWNER, ip="10.0.4.1") as owner,
        person(db_app, mailer, REVIEWER, ip="10.0.4.2") as admin,
    ):
        project = await create_project(owner)
        await add_member(owner, admin, project["id"], REVIEWER, role="admin")
        assert (await delete(admin, f"/projects/{project['id']}")).status_code == 403
        transfer = await post(
            admin, f"/projects/{project['id']}/transfer", {"user_id": str(uuid.uuid4())}
        )
        assert transfer.status_code == 403
        # An admin may still run the review itself.
        assert (
            await patch(admin, f"/projects/{project['id']}", {"title": "Renamed"})
        ).status_code == 200


async def test_an_admin_cannot_change_or_remove_the_owner(
    db_app: FastAPI, mailer: MemoryMailer
) -> None:
    async with (
        person(db_app, mailer, OWNER, ip="10.0.5.1") as owner,
        person(db_app, mailer, REVIEWER, ip="10.0.5.2") as admin,
    ):
        project = await create_project(owner)
        await add_member(owner, admin, project["id"], REVIEWER, role="admin")
        owner_id = (await get(owner, f"/projects/{project['id']}")).json()["owner"]["id"]
        demote = await patch(
            admin, f"/projects/{project['id']}/members/{owner_id}", {"role": "viewer"}
        )
        assert demote.status_code == 409
        assert demote.json()["code"] == "owner_protected"
        assert (
            await delete(admin, f"/projects/{project['id']}/members/{owner_id}")
        ).status_code == 409
        # Nor can an admin make themselves the owner by any route.
        members = (await get(admin, f"/projects/{project['id']}/members")).json()["items"]
        me = next(m["user"]["id"] for m in members if m["role"] == "admin")
        keep = await patch(admin, f"/projects/{project['id']}/members/{me}", {"role": "owner"})
        assert keep.status_code == 422  # "owner" is not a role anyone can assign


async def test_nobody_changes_their_own_role(db_app: FastAPI, mailer: MemoryMailer) -> None:
    async with (
        person(db_app, mailer, OWNER, ip="10.0.6.1") as owner,
        person(db_app, mailer, REVIEWER, ip="10.0.6.2") as admin,
    ):
        project = await create_project(owner)
        await add_member(owner, admin, project["id"], REVIEWER, role="admin")
        members = (await get(admin, f"/projects/{project['id']}/members")).json()["items"]
        me = next(m["user"]["id"] for m in members if m["role"] == "admin")
        response = await patch(
            admin, f"/projects/{project['id']}/members/{me}", {"role": "reviewer"}
        )
        assert response.status_code == 409


async def test_ids_from_another_review_are_not_found(db_app: FastAPI, mailer: MemoryMailer) -> None:
    """Guide 12.2: every object is loaded inside the verified project."""
    async with person(db_app, mailer, OWNER) as owner:
        mine = await create_project(owner, "Mine")
        other = await create_project(owner, "Other")
        criterion = (
            await post(
                owner,
                f"/projects/{other['id']}/criteria",
                {"kind": "inclusion", "text": "Adults over 18"},
            )
        ).json()
        label = (
            await post(owner, f"/projects/{other['id']}/labels", {"name": "RCT", "color": "blue"})
        ).json()
        reason = (await get(owner, f"/projects/{other['id']}/exclusion-reasons")).json()[0]
        group = (
            await post(owner, f"/projects/{other['id']}/keyword-groups", {"name": "Population"})
        ).json()
        for path, body in (
            (f"/projects/{mine['id']}/criteria/{criterion['id']}", {"text": "Changed"}),
            (f"/projects/{mine['id']}/labels/{label['id']}", {"name": "Changed"}),
            (f"/projects/{mine['id']}/exclusion-reasons/{reason['id']}", {"label": "Changed"}),
            (f"/projects/{mine['id']}/keyword-groups/{group['id']}", {"name": "Changed"}),
        ):
            assert (await patch(owner, path, body)).status_code == 404, path
            assert (await delete(owner, path)).status_code == 404, path
        # A keyword may only be added to a group in the same review.
        keywords = await post(
            owner, f"/projects/{mine['id']}/keywords", {"group_id": group["id"], "terms": ["shift"]}
        )
        assert keywords.status_code == 404
        assert (await get(owner, f"/projects/{other['id']}/criteria")).json()[0]["text"] == (
            "Adults over 18"
        )


# --- Invitations -------------------------------------------------------------------------


async def test_an_invitation_only_works_for_the_address_it_was_sent_to(
    db_app: FastAPI, mailer: MemoryMailer
) -> None:
    async with (
        person(db_app, mailer, OWNER, ip="10.0.7.1") as owner,
        person(db_app, mailer, STRANGER, ip="10.0.7.2") as stranger,
    ):
        project = await create_project(owner)
        created = await invite(owner, project["id"], REVIEWER)
        token = token_from(created["link"])
        response = await post(stranger, f"/invites/{token}/accept")
        assert response.status_code == 403
        assert response.json()["code"] == "invite_email_mismatch"
        assert (await get(stranger, f"/projects/{project['id']}")).status_code == 404


async def test_an_unconfirmed_address_cannot_join(db_app: FastAPI, mailer: MemoryMailer) -> None:
    async with person(db_app, mailer, OWNER, ip="10.0.8.1") as owner:
        project = await create_project(owner)
        created = await invite(owner, project["id"], REVIEWER)
        async with make_client(db_app, ip="10.0.8.2") as joiner:
            assert (await register(joiner, REVIEWER)).status_code == 202
            assert (await login(joiner, REVIEWER)).status_code == 200
            response = await post(joiner, f"/invites/{token_from(created['link'])}/accept")
            assert response.status_code == 403
            assert response.json()["code"] == "email_unverified"


async def test_an_invitation_is_single_use_and_can_be_withdrawn(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with (
        person(db_app, mailer, OWNER, ip="10.0.9.1") as owner,
        person(db_app, mailer, REVIEWER, ip="10.0.9.2") as member,
    ):
        project = await create_project(owner)
        created = await invite(owner, project["id"], REVIEWER)
        token = token_from(created["link"])
        # Only a hash of the token is stored (guide 12.1).
        stored = (await db.scalars(select(ProjectInvite.token_hash))).all()
        assert token not in stored
        assert (await post(member, f"/invites/{token}/accept")).status_code == 200
        second = await post(member, f"/invites/{token}/accept")
        assert second.status_code == 200  # already a member: harmless
        assert second.json()["project_id"] == project["id"]

        # A withdrawn invitation stops working.
        again = await invite(owner, project["id"], STRANGER)
        await delete(owner, f"/projects/{project['id']}/invites/{again['id']}")
        preview = await get(owner, f"/invites/{token_from(again['link'])}")
        assert preview.status_code == 400
        assert preview.json()["code"] == "invalid_token"


async def test_an_expired_invitation_is_refused(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with (
        person(db_app, mailer, OWNER, ip="10.0.10.1") as owner,
        person(db_app, mailer, REVIEWER, ip="10.0.10.2") as member,
    ):
        project = await create_project(owner)
        created = await invite(owner, project["id"], REVIEWER)
        stored = await db.scalar(
            select(ProjectInvite).where(ProjectInvite.id == uuid.UUID(created["id"]))
        )
        assert stored is not None
        stored.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await db.commit()
        token = token_from(created["link"])
        assert (await get(member, f"/invites/{token}")).json()["state"] == "expired"
        response = await post(member, f"/invites/{token}/accept")
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_token"


async def test_the_invitation_page_masks_the_address(
    db_app: FastAPI, db_client: AsyncClient, mailer: MemoryMailer
) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner, "Shift work and sleep")
        created = await invite(owner, project["id"], REVIEWER, role="viewer")
    # Signed out, with only the link.
    preview = await get(db_client, f"/invites/{token_from(created['link'])}")
    assert preview.status_code == 200
    assert preview.json() | {"expires_at": ""} == {
        "project_title": "Shift work and sleep",
        "inviter_name": "Ada Lovelace",
        "role": "viewer",
        "email_hint": "g•••@example.org",
        "expires_at": "",
        "state": "pending",
    }


# --- The audit trail ---------------------------------------------------------------------


async def test_team_and_settings_changes_are_audited(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with (
        person(db_app, mailer, OWNER, ip="10.0.11.1") as owner,
        person(db_app, mailer, REVIEWER, ip="10.0.11.2") as member,
    ):
        project = await create_project(owner)
        await add_member(owner, member, project["id"], REVIEWER)
        joined = (await get(owner, f"/projects/{project['id']}/members")).json()["items"][1]
        await patch(
            owner, f"/projects/{project['id']}/members/{joined['user']['id']}", {"role": "admin"}
        )
        await patch(owner, f"/projects/{project['id']}", {"settings": {"blind_mode": False}})
        actions = (
            await db.scalars(
                select(AuditLog.action)
                .where(AuditLog.project_id == uuid.UUID(project["id"]))
                .order_by(AuditLog.id)
            )
        ).all()
        assert list(actions) == [
            "project.created",
            "member.invited",
            "member.joined",
            "member.role_changed",
            "project.settings_changed",
            "project.blind_mode_changed",
        ]
        entry = await db.scalar(
            select(AuditLog).where(AuditLog.action == "project.blind_mode_changed")
        )
        assert entry is not None
        assert entry.before == {"blind_mode": True}
        assert entry.after == {"blind_mode": False}


async def test_membership_rows_go_with_a_removed_member(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with (
        person(db_app, mailer, OWNER, ip="10.0.12.1") as owner,
        person(db_app, mailer, REVIEWER, ip="10.0.12.2") as member,
    ):
        project = await create_project(owner)
        await add_member(owner, member, project["id"], REVIEWER)
        members = (await get(owner, f"/projects/{project['id']}/members")).json()["items"]
        removed = members[1]["user"]["id"]
        assert (
            await delete(owner, f"/projects/{project['id']}/members/{removed}")
        ).status_code == 204
        assert (await get(member, f"/projects/{project['id']}")).status_code == 404
        left = await db.scalars(
            select(ProjectMember).where(ProjectMember.project_id == uuid.UUID(project["id"]))
        )
        assert len(left.all()) == 1
