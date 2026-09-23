"""Blind mode (guide 8.6, 12.10): a blinded reviewer can learn nothing of anyone else's
decisions — not from the queue, a record, the records list, its filters or counts, the
progress bar, the conflicts page, labels or the live event stream."""

import uuid

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import events
from tests.conftest import MemoryMailer
from tests.project_helpers import api, get, post
from tests.screening_helpers import Team, decide, settings, team


async def _split_decisions(t: Team) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """The reviewer includes one record; the owner disagrees on it and excludes another."""
    disputed, owner_only, untouched = t.records[:3]
    await decide(t.reviewer, t.pid, disputed, "include")
    await decide(t.owner, t.pid, disputed, "exclude", note="Wrong population, surely.")
    await decide(t.owner, t.pid, owner_only, "exclude")
    return disputed, owner_only, untouched


async def test_the_screen_shows_a_blinded_reviewer_only_their_own_decision(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer) as t:
        disputed, owner_only, _ = await _split_decisions(t)
        item = (await get(t.reviewer, f"/projects/{t.pid}/screening/records/{disputed}")).json()
        assert item["others"] is None
        assert item["my_decision"]["decision"] == "include"
        queued = (await get(t.reviewer, f"/projects/{t.pid}/screening/queue")).json()
        assert all(entry["others"] is None for entry in queued["items"])
        assert str(owner_only) in {entry["id"] for entry in queued["items"]}
        # The owner, who switched off "Keep me blind too", sees both.
        seen = (await get(t.owner, f"/projects/{t.pid}/screening/records/{disputed}")).json()
        assert [other["decision"] for other in seen["others"]] == ["include"]


async def test_the_records_list_does_not_give_the_final_status_away(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    """The final status is computed from everyone's decisions: "conflict" on a record I
    included tells me someone excluded it. A blinded reviewer sees their own decision."""
    async with team(db_app, db, mailer) as t:
        disputed, owner_only, _ = await _split_decisions(t)
        rows = (await get(t.reviewer, f"/projects/{t.pid}/records")).json()["items"]
        statuses = {row["id"]: row["ta_final"] for row in rows}
        assert statuses[str(disputed)] == "included"
        assert statuses[str(owner_only)] == "pending"
        detail = (await get(t.reviewer, f"/projects/{t.pid}/records/{disputed}")).json()
        assert detail["ta_final"] == "included"

        conflicts = (await get(t.reviewer, f"/projects/{t.pid}/records?status=conflict")).json()
        assert conflicts["items"] == []
        excluded = (await get(t.reviewer, f"/projects/{t.pid}/records?status=excluded")).json()
        assert excluded["items"] == []

        facets = (await get(t.reviewer, f"/projects/{t.pid}/records/facets")).json()
        counts = {count["value"]: count["count"] for count in facets["title_abstract"]}
        assert counts == {"pending": 3, "included": 1}
        assert facets["full_text"] == []

        # Someone who may see it gets the truth.
        truth = (await get(t.owner, f"/projects/{t.pid}/records/{disputed}")).json()
        assert truth["ta_final"] == "conflict"


async def test_progress_and_conflicts_stay_closed_to_a_blinded_reviewer(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer) as t:
        await _split_decisions(t)
        progress = (await get(t.reviewer, f"/projects/{t.pid}/screening/progress")).json()
        assert progress["conflicts"] is None
        assert progress["blind"] is True
        assert (progress["screened"], progress["included"]) == (1, 1)
        assert (await get(t.reviewer, f"/projects/{t.pid}/conflicts")).status_code == 403
        owner_view = (await get(t.owner, f"/projects/{t.pid}/screening/progress")).json()
        assert owner_view["conflicts"] == 1


async def test_labels_and_decision_notes_are_blinded_but_team_notes_are_shared(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer) as t:
        record = t.records[0]
        label = (
            await post(t.owner, f"/projects/{t.pid}/labels", {"name": "Exclude?", "color": "red"})
        ).json()
        await api(
            t.owner,
            "PUT",
            f"/projects/{t.pid}/records/{record}/labels",
            {"label_ids": [label["id"]]},
        )
        await decide(t.owner, t.pid, record, "exclude", note="Not nurses.")
        await post(
            t.owner,
            f"/projects/{t.pid}/records/{record}/notes",
            {"body": "Shared thought.", "visibility": "team"},
        )

        item = (await get(t.reviewer, f"/projects/{t.pid}/screening/records/{record}")).json()
        assert item["labels"] == []
        assert item["others"] is None
        assert [note["body"] for note in item["notes"]] == ["Shared thought."]
        # Nor can the label be found by name.
        found = (await get(t.reviewer, f"/projects/{t.pid}/records?q=label:Exclude%3F")).json()
        assert found["items"] == []


async def test_the_event_stream_carries_no_decisions(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer) as t:
        await _split_decisions(t)
        recent = await events.recent(db_app.state.redis, uuid.UUID(t.pid))
        assert not any("decision" in payload for payload in recent)


async def test_an_owner_who_keeps_themselves_blind_is_blind(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    """Guide 7: owners and admins who also screen stay blind by default."""
    async with team(db_app, db, mailer, unblind_owner=False) as t:
        record = t.records[0]
        await decide(t.reviewer, t.pid, record, "include")
        item = (await get(t.owner, f"/projects/{t.pid}/screening/records/{record}")).json()
        assert item["others"] is None
        rows = (await get(t.owner, f"/projects/{t.pid}/records")).json()["items"]
        assert {row["ta_final"] for row in rows} == {"pending"}


async def test_with_blind_mode_off_everyone_sees_everything(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer) as t:
        disputed, _, _ = await _split_decisions(t)
        await settings(t.owner, t.pid, blind_mode=False)
        item = (await get(t.reviewer, f"/projects/{t.pid}/screening/records/{disputed}")).json()
        assert [(o["decision"], o["note"]) for o in item["others"]] == [
            ("exclude", "Wrong population, surely.")
        ]
        detail = (await get(t.reviewer, f"/projects/{t.pid}/records/{disputed}")).json()
        assert detail["ta_final"] == "conflict"
