"""Criteria, keyword groups, exclusion reasons and labels (guide 8.2)."""

from fastapi import FastAPI

from tests.conftest import MemoryMailer
from tests.project_helpers import OWNER, create_project, delete, get, patch, person, post


async def test_criteria_keep_their_own_order_per_kind(
    db_app: FastAPI, mailer: MemoryMailer
) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        path = f"/projects/{project['id']}/criteria"
        for text in ("Adults over 18", "Randomised trials", "Published since 2010"):
            assert (await post(owner, path, {"kind": "inclusion", "text": text})).status_code == 201
        excluded = (await post(owner, path, {"kind": "exclusion", "text": "Animal studies"})).json()
        assert excluded["position"] == 0

        listed = (await get(owner, path)).json()
        assert [(c["kind"], c["position"]) for c in listed] == [
            ("inclusion", 0),
            ("inclusion", 1),
            ("inclusion", 2),
            ("exclusion", 0),
        ]

        # Move the third inclusion criterion to the top.
        third = listed[2]
        moved = await patch(owner, f"{path}/{third['id']}", {"position": 0})
        assert moved.status_code == 200
        assert [c["text"] for c in (await get(owner, path)).json()[:3]] == [
            "Published since 2010",
            "Adults over 18",
            "Randomised trials",
        ]

        # Move one across to the exclusion list; both lists stay numbered from zero.
        await patch(owner, f"{path}/{third['id']}", {"kind": "exclusion"})
        after = (await get(owner, path)).json()
        assert [(c["kind"], c["position"], c["text"]) for c in after] == [
            ("inclusion", 0, "Adults over 18"),
            ("inclusion", 1, "Randomised trials"),
            ("exclusion", 0, "Animal studies"),
            ("exclusion", 1, "Published since 2010"),
        ]

        assert (await delete(owner, f"{path}/{after[0]['id']}")).status_code == 204
        assert [c["position"] for c in (await get(owner, path)).json()] == [0, 0, 1]
        assert (await post(owner, path, {"kind": "inclusion", "text": " "})).status_code == 422


async def test_keyword_groups_hold_their_keywords(db_app: FastAPI, mailer: MemoryMailer) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        groups_path = f"/projects/{project['id']}/keyword-groups"
        group = (await post(owner, groups_path, {"name": "Population", "color": "teal"})).json()
        assert group["kind"] == "include"
        assert group["keywords"] == []

        added = await post(
            owner,
            f"/projects/{project['id']}/keywords",
            {"group_id": group["id"], "terms": ["nurses", "shift workers", "NURSES"]},
        )
        assert added.status_code == 201
        # The repeat is skipped, whatever its capitalisation.
        assert [k["term"] for k in added.json()["keywords"]] == ["nurses", "shift workers"]

        keyword = added.json()["keywords"][0]
        renamed = await patch(
            owner,
            f"/projects/{project['id']}/keywords/{keyword['id']}",
            {"term": "registered nurses", "whole_word": False},
        )
        assert renamed.status_code == 200
        assert renamed.json()["term"] == "registered nurses"
        assert renamed.json()["whole_word"] is False
        clash = await patch(
            owner,
            f"/projects/{project['id']}/keywords/{keyword['id']}",
            {"term": "Shift Workers"},
        )
        assert clash.status_code == 409

        updated = await patch(owner, f"{groups_path}/{group['id']}", {"kind": "exclude"})
        assert updated.json()["kind"] == "exclude"
        assert (await delete(owner, f"{groups_path}/{group['id']}")).status_code == 204
        assert (await get(owner, groups_path)).json() == []


async def test_a_keyword_pattern_must_be_safe(db_app: FastAPI, mailer: MemoryMailer) -> None:
    """Guide 12.3: patterns are limited to a subset that cannot backtrack for ever."""
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        group = (
            await post(owner, f"/projects/{project['id']}/keyword-groups", {"name": "Terms"})
        ).json()
        path = f"/projects/{project['id']}/keywords"

        good = await post(
            owner,
            path,
            {"group_id": group["id"], "terms": [r"randomi[sz]ed", r"\bRCTs?\b"], "is_regex": True},
        )
        assert good.status_code == 201
        assert len(good.json()["keywords"]) == 2

        evil = await post(
            owner, path, {"group_id": group["id"], "terms": [r"(a+)+b"], "is_regex": True}
        )
        assert evil.status_code == 422
        assert evil.json()["code"] == "invalid_pattern"
        assert "repeat" in evil.json()["detail"]
        # Nothing was stored from the refused call.
        assert (
            len(
                (await get(owner, f"/projects/{project['id']}/keyword-groups")).json()[0][
                    "keywords"
                ]
            )
            == 2
        )
        # A plain term is never treated as a pattern.
        plain = await post(owner, path, {"group_id": group["id"], "terms": ["(a+)+b"]})
        assert plain.status_code == 201


async def test_exclusion_reasons_can_be_edited_and_reordered(
    db_app: FastAPI, mailer: MemoryMailer
) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        path = f"/projects/{project['id']}/exclusion-reasons"
        before = (await get(owner, path)).json()

        added = await post(owner, path, {"label": "Protocol only", "stage": "title_abstract"})
        assert added.status_code == 201
        assert added.json()["position"] == len(before)

        duplicate = await post(owner, path, {"label": "protocol only"})
        assert duplicate.status_code == 409
        assert duplicate.json()["code"] == "duplicate"

        moved = await patch(owner, f"{path}/{added.json()['id']}", {"position": 0})
        assert moved.status_code == 200
        listed = (await get(owner, path)).json()
        assert listed[0]["label"] == "Protocol only"
        assert [r["position"] for r in listed] == list(range(len(listed)))

        assert (await delete(owner, f"{path}/{listed[0]['id']}")).status_code == 204
        assert [r["label"] for r in (await get(owner, path)).json()] == [r["label"] for r in before]


async def test_labels_have_unique_names_and_a_colour(db_app: FastAPI, mailer: MemoryMailer) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        path = f"/projects/{project['id']}/labels"
        created = await post(owner, path, {"name": "Key paper", "color": "violet"})
        assert created.status_code == 201
        assert created.json()["color"] == "violet"

        assert (await post(owner, path, {"name": "key paper"})).status_code == 409
        assert (await post(owner, path, {"name": "Other", "color": "neon"})).status_code == 422

        renamed = await patch(owner, f"{path}/{created.json()['id']}", {"name": "Landmark"})
        assert renamed.json()["name"] == "Landmark"
        assert (await delete(owner, f"{path}/{created.json()['id']}")).status_code == 204
        assert (await get(owner, path)).json() == []


async def test_text_fields_reject_control_characters(db_app: FastAPI, mailer: MemoryMailer) -> None:
    """Guide 12.3: a title with a line break could smuggle a header into an email."""
    async with person(db_app, mailer, OWNER) as owner:
        assert (
            await post(owner, "/projects", {"title": "Sleep\nBcc: someone@example.org"})
        ).status_code == 422
        project = await create_project(owner)
        assert (
            await post(owner, f"/projects/{project['id']}/labels", {"name": "a‮b"})
        ).status_code == 422
