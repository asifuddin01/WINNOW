"""Creating, listing, editing, transferring and copying reviews (guide 8.2)."""

import uuid

import pytest
from fastapi import FastAPI

from app.main import create_app
from app.services.projects import DEFAULT_EXCLUSION_REASONS
from tests.auth_helpers import enable_two_factor, login, register
from tests.conftest import MemoryMailer, make_client, make_settings
from tests.project_helpers import (
    OWNER,
    REVIEWER,
    add_member,
    create_project,
    delete,
    get,
    patch,
    person,
    post,
)


async def test_a_new_review_starts_ready_to_use(db_app: FastAPI, mailer: MemoryMailer) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(
            owner,
            "Night shifts and sleep quality",
            review_type="scoping",
            research_question="Do night shifts affect sleep quality in nurses?",
            pico={"population": "Nurses", "intervention": "Night shifts"},
        )
        assert project["status"] == "setup"
        assert project["review_type"] == "scoping"
        assert project["membership"]["role"] == "owner"
        assert project["member_count"] == 1
        assert project["owner"]["email"] == OWNER
        assert project["pico"]["population"] == "Nurses"
        assert project["pico"]["outcome"] is None
        # Guide 6.2 defaults.
        assert project["settings"] == {
            "blind_mode": True,
            "reviewers_per_record_ta": 2,
            "reviewers_per_record_ft": 2,
            "maybe_counts_as": "include",
            "require_reason_on_exclude_ta": False,
            "require_reason_on_exclude_ft": True,
            "ranking_enabled": True,
            "llm_assist_enabled": False,
            "dedup_on_import": True,
            "dedup_auto_resolve": True,
            "stopping_rule": {"type": "consecutive_excludes", "n": 200},
            "assignment": "all",
            "highlight_keywords": True,
        }
        # Guide 8.2: the standard exclusion reasons are there from the start.
        reasons = (await get(owner, f"/projects/{project['id']}/exclusion-reasons")).json()
        assert [reason["label"] for reason in reasons] == [
            label for label, _ in DEFAULT_EXCLUSION_REASONS
        ]
        assert reasons[-1]["stage"] == "full_text"


async def test_the_dashboard_lists_my_reviews_newest_first(
    db_app: FastAPI, mailer: MemoryMailer
) -> None:
    async with (
        person(db_app, mailer, OWNER, ip="10.1.0.1") as owner,
        person(db_app, mailer, REVIEWER, ip="10.1.0.2") as other,
    ):
        first = await create_project(owner, "First")
        second = await create_project(owner, "Second")
        await create_project(other, "Not mine")
        await add_member(owner, other, second["id"], REVIEWER, role="viewer")

        mine = (await get(owner, "/projects")).json()
        assert [p["title"] for p in mine["items"]] == ["Second", "First"]
        assert mine["next_cursor"] is None
        assert mine["items"][0]["member_count"] == 2
        assert mine["items"][0]["role"] == "owner"

        theirs = (await get(other, "/projects")).json()["items"]
        assert [(p["title"], p["role"]) for p in theirs] == [
            ("Not mine", "owner"),
            ("Second", "viewer"),
        ]
        assert first["id"] not in [p["id"] for p in theirs]


async def test_the_dashboard_pages_through_long_lists(
    db_app: FastAPI, mailer: MemoryMailer
) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        for index in range(3):
            await create_project(owner, f"Review {index}")
        first = (await get(owner, "/projects?limit=2")).json()
        assert [p["title"] for p in first["items"]] == ["Review 2", "Review 1"]
        assert first["next_cursor"]
        second = (await get(owner, f"/projects?limit=2&cursor={first['next_cursor']}")).json()
        assert [p["title"] for p in second["items"]] == ["Review 0"]
        assert second["next_cursor"] is None
        assert (await get(owner, "/projects?cursor=nonsense")).status_code == 400


async def test_editing_the_basics_and_the_settings(db_app: FastAPI, mailer: MemoryMailer) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner, "Working title")
        updated = await patch(
            owner,
            f"/projects/{project['id']}",
            {
                "title": "Shift work and sleep",
                "description": "  A scoping review.  ",
                "status": "screening",
                "settings": {"blind_mode": False, "reviewers_per_record_ta": 1},
            },
        )
        assert updated.status_code == 200
        body = updated.json()
        assert body["title"] == "Shift work and sleep"
        assert body["description"] == "A scoping review."
        assert body["status"] == "screening"
        assert body["settings"]["blind_mode"] is False
        assert body["settings"]["reviewers_per_record_ta"] == 1
        assert body["settings"]["reviewers_per_record_ft"] == 2  # untouched
        # Clearing an optional field.
        cleared = await patch(owner, f"/projects/{project['id']}", {"description": ""})
        assert cleared.json()["description"] is None
        # Nonsense is refused.
        assert (
            await patch(owner, f"/projects/{project['id']}", {"title": "   "})
        ).status_code == 422
        assert (
            await patch(owner, f"/projects/{project['id']}", {"settings": {"nope": True}})
        ).status_code == 422
        assert (
            await patch(
                owner, f"/projects/{project['id']}", {"settings": {"reviewers_per_record_ta": 9}}
            )
        ).status_code == 422


async def test_ai_assist_needs_a_provider_on_the_instance(
    db_app: FastAPI, mailer: MemoryMailer
) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        response = await patch(
            owner, f"/projects/{project['id']}", {"settings": {"llm_assist_enabled": True}}
        )
        assert response.status_code == 409
        assert response.json()["code"] == "feature_unavailable"


async def test_transferring_a_review(db_app: FastAPI, mailer: MemoryMailer) -> None:
    async with (
        person(db_app, mailer, OWNER, ip="10.1.1.1") as owner,
        person(db_app, mailer, REVIEWER, ip="10.1.1.2") as heir,
    ):
        project = await create_project(owner)
        await add_member(owner, heir, project["id"], REVIEWER, role="admin")
        members = (await get(owner, f"/projects/{project['id']}/members")).json()["items"]
        heir_id = next(m["user"]["id"] for m in members if m["role"] == "admin")

        response = await post(owner, f"/projects/{project['id']}/transfer", {"user_id": heir_id})
        assert response.status_code == 200
        assert response.json()["owner"]["id"] == heir_id
        assert response.json()["membership"]["role"] == "admin"  # the old owner stays on
        assert (await get(heir, f"/projects/{project['id']}")).json()["membership"]["role"] == (
            "owner"
        )
        # Now only the new owner may delete it.
        assert (await delete(owner, f"/projects/{project['id']}")).status_code == 403
        assert (await delete(heir, f"/projects/{project['id']}")).status_code == 204


async def test_a_review_can_only_be_handed_to_a_member(
    db_app: FastAPI, mailer: MemoryMailer
) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        stranger = await post(
            owner, f"/projects/{project['id']}/transfer", {"user_id": str(uuid.uuid4())}
        )
        assert stranger.status_code == 404
        members = (await get(owner, f"/projects/{project['id']}/members")).json()["items"]
        mine = await post(
            owner, f"/projects/{project['id']}/transfer", {"user_id": members[0]["user"]["id"]}
        )
        assert mine.status_code == 409


async def test_the_owner_cannot_leave_or_be_removed(db_app: FastAPI, mailer: MemoryMailer) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        response = await delete(owner, f"/projects/{project['id']}/membership")
        assert response.status_code == 409
        assert response.json()["code"] == "owner_protected"


async def test_copying_a_setup_into_a_new_review(db_app: FastAPI, mailer: MemoryMailer) -> None:
    async with (
        person(db_app, mailer, OWNER, ip="10.1.2.1") as owner,
        person(db_app, mailer, REVIEWER, ip="10.1.2.2") as member,
    ):
        source = await create_project(owner, "Template review", review_type="rapid")
        await patch(owner, f"/projects/{source['id']}", {"settings": {"blind_mode": False}})
        await post(
            owner, f"/projects/{source['id']}/criteria", {"kind": "inclusion", "text": "Adults"}
        )
        group = (
            await post(owner, f"/projects/{source['id']}/keyword-groups", {"name": "Population"})
        ).json()
        await post(
            owner,
            f"/projects/{source['id']}/keywords",
            {"group_id": group["id"], "terms": ["nurses", "shift workers"]},
        )
        await post(owner, f"/projects/{source['id']}/labels", {"name": "RCT", "color": "green"})
        await add_member(owner, member, source["id"], REVIEWER, role="viewer")

        # Even a viewer can start their own review from the setup they can already read.
        copy = await post(
            member, f"/projects/{source['id']}/duplicate-setup", {"title": "My own review"}
        )
        assert copy.status_code == 201
        new = copy.json()
        assert new["title"] == "My own review"
        assert new["review_type"] == "rapid"
        assert new["membership"]["role"] == "owner"
        assert new["member_count"] == 1
        assert new["settings"]["blind_mode"] is False
        assert [
            c["text"] for c in (await get(member, f"/projects/{new['id']}/criteria")).json()
        ] == ["Adults"]
        groups = (await get(member, f"/projects/{new['id']}/keyword-groups")).json()
        assert [k["term"] for k in groups[0]["keywords"]] == ["nurses", "shift workers"]
        assert groups[0]["id"] != group["id"]
        assert [
            lab["name"] for lab in (await get(member, f"/projects/{new['id']}/labels")).json()
        ] == ["RCT"]
        reasons = (await get(member, f"/projects/{new['id']}/exclusion-reasons")).json()
        assert len(reasons) == len(DEFAULT_EXCLUSION_REASONS)


async def test_an_unconfirmed_address_cannot_start_a_review(
    db_app: FastAPI, mailer: MemoryMailer
) -> None:
    async with make_client(db_app) as client:
        assert (await register(client, OWNER)).status_code == 202
        assert (await login(client, OWNER)).status_code == 200
        response = await post(client, "/projects", {"title": "Too soon"})
        assert response.status_code == 403
        assert response.json()["code"] == "email_unverified"


@pytest.mark.parametrize("two_factor", [False, True])
async def test_owner_two_factor_can_be_required(
    db_app: FastAPI, mailer: MemoryMailer, two_factor: bool
) -> None:
    """Guide 2.1: an instance can insist that review owners use 2FA."""
    settings = make_settings(
        database_url=db_app.state.settings.database_url,
        redis_url=db_app.state.settings.redis_url,
        require_owner_2fa=True,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.sessionmaker = db_app.state.sessionmaker
        app.state.mailer = mailer
        async with person(app, mailer, OWNER) as owner:
            if two_factor:
                await enable_two_factor(owner)
            response = await post(owner, "/projects", {"title": "Protected"})
            assert response.status_code == (201 if two_factor else 403)
            if not two_factor:
                assert response.json()["code"] == "two_factor_required"


async def test_single_user_instances_need_only_one_reviewer(
    db_app: FastAPI, mailer: MemoryMailer
) -> None:
    settings = make_settings(
        database_url=db_app.state.settings.database_url,
        redis_url=db_app.state.settings.redis_url,
        winnow_single_user=True,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.sessionmaker = db_app.state.sessionmaker
        app.state.mailer = mailer
        async with make_client(app) as client:
            setup = await post(
                client,
                "/auth/setup",
                {"name": "Solo", "email": OWNER, "password": "a sturdy passphrase for tests"},
            )
            assert setup.status_code == 201, setup.text
            project = await create_project(client, "Just me")
            assert project["settings"]["reviewers_per_record_ta"] == 1
            assert project["settings"]["reviewers_per_record_ft"] == 1
            invited = await post(client, f"/projects/{project['id']}/invites", {"email": REVIEWER})
            assert invited.status_code == 409
            assert invited.json()["code"] == "invites_unavailable"
