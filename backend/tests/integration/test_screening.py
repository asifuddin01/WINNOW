"""Screening end to end: decisions and the status rule, the queue, undo, history,
reasons, labels, notes, assignment, bulk decisions and conflicts (guide 8.5-8.7, 6.4)."""

import uuid
from collections import Counter

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, ConflictResolution, Decision, ResolutionSource
from tests.conftest import MemoryMailer
from tests.project_helpers import api, get, post
from tests.screening_helpers import add_records, decide, settings, status_of, team


async def test_two_reviewers_who_agree_decide_the_record(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer) as t:
        first, second = t.records[:2]
        assert (await decide(t.reviewer, t.pid, first, "include")).status_code == 200
        # One of the two decisions the review asks for: still pending (guide 6.4 rule 2).
        assert await status_of(t.owner, t.pid, first) == "pending"
        await decide(t.owner, t.pid, first, "include")
        assert await status_of(t.owner, t.pid, first) == "included"

        await decide(t.reviewer, t.pid, second, "include")
        await decide(t.owner, t.pid, second, "exclude")
        assert await status_of(t.owner, t.pid, second) == "conflict"


@pytest.mark.parametrize(
    ("counts_as", "expected"), [("include", "included"), ("maybe", "conflict")]
)
async def test_a_maybe_counts_as_the_review_says(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, counts_as: str, expected: str
) -> None:
    async with team(db_app, db, mailer) as t:
        await settings(t.owner, t.pid, maybe_counts_as=counts_as)
        record = t.records[0]
        await decide(t.reviewer, t.pid, record, "maybe")
        await decide(t.owner, t.pid, record, "include")
        assert await status_of(t.owner, t.pid, record) == expected


async def test_changing_how_many_reviewers_a_record_needs_recomputes_every_status(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer) as t:
        record = t.records[0]
        await decide(t.reviewer, t.pid, record, "exclude")
        assert await status_of(t.owner, t.pid, record) == "pending"
        await settings(t.owner, t.pid, reviewers_per_record_ta=1)
        assert await status_of(t.owner, t.pid, record) == "excluded"


async def test_an_include_at_title_abstract_opens_the_full_text_stage_and_undo_closes_it(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer) as t:
        await settings(t.owner, t.pid, reviewers_per_record_ta=1)
        record = t.records[0]
        await decide(t.reviewer, t.pid, record, "include")
        detail = (await get(t.owner, f"/projects/{t.pid}/records/{record}")).json()
        assert (detail["ta_final"], detail["ft_final"]) == ("included", "pending")

        undone = await api(t.reviewer, "DELETE", f"/projects/{t.pid}/records/{record}/decision")
        assert undone.status_code == 200
        assert undone.json()["decision"] is None
        detail = (await get(t.owner, f"/projects/{t.pid}/records/{record}")).json()
        assert (detail["ta_final"], detail["ft_final"]) == ("pending", "not_eligible")


async def test_the_queue_holds_what_is_left_for_me_in_a_stable_order(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=6) as t:
        queue = (
            await get(t.reviewer, f"/projects/{t.pid}/screening/queue?n=10&sort=random")
        ).json()
        order = [item["id"] for item in queue["items"]]
        assert sorted(order) == sorted(str(record) for record in t.records)
        # Random per person, but the same order every time: the records held ahead of the
        # one on screen do not reshuffle.
        again = (
            await get(t.reviewer, f"/projects/{t.pid}/screening/queue?n=10&sort=random")
        ).json()
        assert [item["id"] for item in again["items"]] == order

        await decide(t.reviewer, t.pid, uuid.UUID(order[0]), "exclude")
        # The records the screen already holds are left out when it asks for more.
        held = "&".join(f"exclude={record}" for record in order[1:3])
        more = (
            await get(t.reviewer, f"/projects/{t.pid}/screening/queue?n=10&sort=random&{held}")
        ).json()
        assert [item["id"] for item in more["items"]] == order[3:]

        # In "all" mode the other reviewer still sees every record.
        theirs = (await get(t.owner, f"/projects/{t.pid}/screening/queue?n=10")).json()
        assert len(theirs["items"]) == 6


async def test_the_history_lists_my_decisions_and_any_can_be_revisited(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer) as t:
        first, second = t.records[:2]
        await decide(t.reviewer, t.pid, first, "include")
        await decide(t.reviewer, t.pid, second, "maybe", note="Check the population.")
        history = (await get(t.reviewer, f"/projects/{t.pid}/my-history")).json()
        assert [item["record_id"] for item in history["items"]] == [str(second), str(first)]

        revisit = (await get(t.reviewer, f"/projects/{t.pid}/screening/records/{second}")).json()
        assert revisit["my_decision"]["decision"] == "maybe"
        assert revisit["my_decision"]["note"] == "Check the population."
        changed = await decide(t.reviewer, t.pid, second, "exclude")
        assert changed.json()["decision"]["decision"] == "exclude"
        history = (await get(t.reviewer, f"/projects/{t.pid}/my-history")).json()
        assert history["items"][0] == {
            **history["items"][0],
            "record_id": str(second),
            "decision": "exclude",
        }


async def test_time_on_a_record_adds_up_and_is_capped_per_visit(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer) as t:
        record = t.records[0]
        await decide(t.reviewer, t.pid, record, "maybe", time_spent_ms=12_000)
        await decide(t.reviewer, t.pid, record, "include", time_spent_ms=9_000_000)
        spent = await db.scalar(select(Decision.time_spent_ms).where(Decision.record_id == record))
        assert spent == 12_000 + 30 * 60 * 1000


async def test_exclusion_reasons_belong_to_the_review_and_can_be_required(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer) as t:
        reasons = (await get(t.owner, f"/projects/{t.pid}/exclusion-reasons")).json()
        wrong_population = next(r["id"] for r in reasons if r["label"] == "Wrong population")
        record = t.records[0]

        await settings(t.owner, t.pid, require_reason_on_exclude_ta=True)
        refused = await decide(t.reviewer, t.pid, record, "exclude")
        assert refused.status_code == 422
        assert refused.json()["code"] == "reason_required"

        unknown = await decide(t.reviewer, t.pid, record, "exclude", reason_ids=[str(uuid.uuid4())])
        assert unknown.json()["code"] == "unknown_reason"

        ok = await decide(t.reviewer, t.pid, record, "exclude", reason_ids=[wrong_population])
        assert ok.json()["decision"]["reason_ids"] == [wrong_population]
        # Reasons are for exclusions: an include drops them.
        included = await decide(t.reviewer, t.pid, record, "include", reason_ids=[wrong_population])
        assert included.json()["decision"]["reason_ids"] == []


async def test_notes_are_private_unless_shared_and_labels_are_my_own(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer) as t:
        record = t.records[0]
        path = f"/projects/{t.pid}/records/{record}/notes"
        await post(t.reviewer, path, {"body": "Only for me.", "visibility": "private"})
        await post(t.reviewer, path, {"body": "Team: is this an RCT?", "visibility": "team"})
        mine = (await get(t.reviewer, f"/projects/{t.pid}/screening/records/{record}")).json()
        assert [n["body"] for n in mine["notes"]] == ["Only for me.", "Team: is this an RCT?"]
        theirs = (await get(t.owner, f"/projects/{t.pid}/screening/records/{record}")).json()
        assert [n["body"] for n in theirs["notes"]] == ["Team: is this an RCT?"]
        assert theirs["notes"][0]["mine"] is False

        label = await post(t.owner, f"/projects/{t.pid}/labels", {"name": "RCT", "color": "blue"})
        label_id = label.json()["id"]
        applied = await api(
            t.reviewer,
            "PUT",
            f"/projects/{t.pid}/records/{record}/labels",
            {"label_ids": [label_id]},
        )
        assert applied.json() == [label_id]
        foreign = await api(
            t.reviewer,
            "PUT",
            f"/projects/{t.pid}/records/{record}/labels",
            {"label_ids": [str(uuid.uuid4())]},
        )
        assert foreign.json()["code"] == "unknown_label"
        # label: in the search box finds it.
        found = (await get(t.reviewer, f"/projects/{t.pid}/screening/queue?q=label:RCT")).json()
        assert [item["id"] for item in found["items"]] == [str(record)]


async def test_split_mode_gives_every_record_exactly_n_screeners(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    """Guide 8.5: records are shared out so each gets exactly N reviewers, balanced."""
    async with team(db_app, db, mailer, records=60, third=True) as t:
        assert t.third is not None
        await settings(t.owner, t.pid, assignment="split", reviewers_per_record_ta=2)
        seen: Counter[str] = Counter()
        shares = []
        for client in (t.owner, t.reviewer, t.third):
            page = (await get(client, f"/projects/{t.pid}/screening/queue?n=25")).json()
            progress = (await get(client, f"/projects/{t.pid}/screening/progress")).json()
            shares.append(progress["total"])
            ids = [item["id"] for item in page["items"]]
            while len(ids) < progress["total"]:
                held = "&".join(f"exclude={record}" for record in ids[-60:])
                more = (await get(client, f"/projects/{t.pid}/screening/queue?n=25&{held}")).json()
                if not more["items"]:
                    break
                ids += [item["id"] for item in more["items"]]
            seen.update(ids)
        assert set(seen.values()) == {2}, "every record goes to exactly two screeners"
        assert sum(shares) == 120
        assert all(25 <= share <= 55 for share in shares), shares


async def test_a_bulk_decision_is_confirmed_logged_and_settles_the_records(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=2) as t:
        editorials = await add_records(db, t.pid, 3, publication_type=["Editorial"])
        body = {"final_decision": "exclude", "q": "type:editorial", "expected": 0}
        preview = await post(t.owner, f"/projects/{t.pid}/bulk-decision/preview", body)
        assert preview.json() == {"decided": 3}

        # The count the person saw must still be true when they confirm.
        stale = await post(t.owner, f"/projects/{t.pid}/bulk-decision", {**body, "expected": 2})
        assert stale.status_code == 409
        assert stale.json()["code"] == "bulk_changed"

        done = await post(t.owner, f"/projects/{t.pid}/bulk-decision", {**body, "expected": 3})
        assert done.json() == {"decided": 3}
        for record in editorials:
            assert await status_of(t.owner, t.pid, record) == "excluded"
        sources = set(await db.scalars(select(ConflictResolution.source)))
        assert sources == {ResolutionSource.BULK}
        # Settled records leave everyone's queue.
        queue = (await get(t.reviewer, f"/projects/{t.pid}/screening/queue")).json()
        assert {item["id"] for item in queue["items"]} == {str(r) for r in t.records}
        logged = await db.scalar(select(AuditLog).where(AuditLog.action == "decision.bulk"))
        assert logged is not None
        assert logged.after is not None
        assert logged.after["bulk"] is True
        assert logged.after["count"] == 3

        # Reviewers do not decide in bulk.
        refused = await post(
            t.reviewer, f"/projects/{t.pid}/bulk-decision", {**body, "expected": 0}
        )
        assert refused.status_code == 403


async def test_a_conflict_is_resolved_side_by_side_and_can_be_discussed(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer) as t:
        record = t.records[0]
        await decide(t.reviewer, t.pid, record, "include", note="Adults, night shifts.")
        await decide(t.owner, t.pid, record, "exclude")
        page = (await get(t.owner, f"/projects/{t.pid}/conflicts")).json()
        assert page["total"] == 1
        (item,) = page["items"]
        assert {d["decision"] for d in item["decisions"]} == {"include", "exclude"}
        assert "Adults, night shifts." in {d["note"] for d in item["decisions"]}

        mailer.outbox.clear()
        discussed = await post(
            t.owner, f"/projects/{t.pid}/conflicts/{record}/discuss", {"body": "Population?"}
        )
        assert discussed.status_code == 201
        assert discussed.json()["visibility"] == "team"
        assert [email.to for email in mailer.outbox] == ["grace@example.org"]
        assert "needs a discussion" in mailer.outbox[0].subject

        resolved = await post(
            t.owner,
            f"/projects/{t.pid}/conflicts/{record}/resolve",
            {"final_decision": "include", "note": "Adults on nights: in scope."},
        )
        assert resolved.status_code == 200
        assert resolved.json()["resolution"] == "include"
        assert await status_of(t.owner, t.pid, record) == "included"
        assert (await get(t.owner, f"/projects/{t.pid}/conflicts")).json()["total"] == 0

        # A record the reviewers agree on has nothing to resolve.
        agreed = t.records[1]
        await decide(t.reviewer, t.pid, agreed, "include")
        await decide(t.owner, t.pid, agreed, "include")
        nothing = await post(
            t.owner, f"/projects/{t.pid}/conflicts/{agreed}/resolve", {"final_decision": "exclude"}
        )
        assert nothing.status_code == 409


async def test_only_resolvers_reach_the_conflicts(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer) as t:
        assert (await get(t.reviewer, f"/projects/{t.pid}/conflicts")).status_code == 403
        members = (await get(t.owner, f"/projects/{t.pid}/members")).json()["items"]
        grace = next(m for m in members if m["user"]["email"] == "grace@example.org")
        trusted = await api(
            t.owner,
            "PATCH",
            f"/projects/{t.pid}/members/{grace['user']['id']}",
            {"can_resolve_conflicts": True},
        )
        assert trusted.status_code == 200, trusted.text
        assert (await get(t.reviewer, f"/projects/{t.pid}/conflicts")).status_code == 200


async def test_a_viewer_does_not_screen(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    from tests.project_helpers import add_member, person

    async with (
        team(db_app, db, mailer) as t,
        person(db_app, mailer, "vi@example.org", ip="10.9.0.9") as viewer,
    ):
        await add_member(t.owner, viewer, t.pid, "vi@example.org", role="viewer")
        assert (await get(viewer, f"/projects/{t.pid}/screening/queue")).status_code == 403
        assert (await decide(viewer, t.pid, t.records[0], "include")).status_code == 403


async def test_merging_a_duplicate_brings_its_screening_with_it(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    """Guide 8.4: decisions, labels and notes on a copy move to the record that is kept."""
    from app.models import DupCluster, DupClusterMember
    from app.services.dedup import merge_cluster

    async with team(db_app, db, mailer) as t:
        kept, copy = t.records[:2]
        await decide(t.reviewer, t.pid, copy, "include")
        await post(t.reviewer, f"/projects/{t.pid}/records/{copy}/notes", {"body": "Keep this."})
        cluster = DupCluster(project_id=uuid.UUID(t.pid), score=0.95)
        db.add(cluster)
        await db.flush()
        db.add_all(
            [
                DupClusterMember(cluster_id=cluster.id, record_id=kept, is_primary=True),
                DupClusterMember(cluster_id=cluster.id, record_id=copy),
            ]
        )
        await db.flush()
        await merge_cluster(db, cluster, kept, resolved_by=None)
        await db.commit()

        moved = (await get(t.reviewer, f"/projects/{t.pid}/screening/records/{kept}")).json()
        assert moved["my_decision"]["decision"] == "include"
        assert [note["body"] for note in moved["notes"]] == ["Keep this."]
