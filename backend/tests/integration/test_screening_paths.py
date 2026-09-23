"""The less travelled paths through screening: the full-text stage, the other queue
orders, paging, refusals, and the filters a bulk decision can use."""

import uuid

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import MemoryMailer
from tests.project_helpers import api, get, post
from tests.screening_helpers import decide, settings, status_of, team


async def _ids(client: AsyncClient, path: str) -> list[str]:
    page = (await get(client, path)).json()
    return [item["id"] for item in page["items"]]


async def _me(client: AsyncClient) -> str:
    user_id: str = (await get(client, "/auth/me")).json()["id"]
    return user_id


async def test_the_queue_can_be_read_newest_first_by_title_or_in_import_order(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer) as t:
        # The helper gives record i the year 2015 + i and the title "... study i".
        in_order = [str(record) for record in t.records]
        queue = f"/projects/{t.pid}/screening/queue"
        assert await _ids(t.reviewer, f"{queue}?sort=year") == in_order[::-1]
        assert await _ids(t.reviewer, f"{queue}?sort=title") == in_order
        assert await _ids(t.reviewer, f"{queue}?sort=added") == in_order


async def test_full_text_is_screened_only_once_the_title_and_abstract_are_in(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer) as t:
        await settings(t.owner, t.pid, reviewers_per_record_ta=1, reviewers_per_record_ft=1)
        record = t.records[0]
        early = await decide(t.reviewer, t.pid, record, "include", stage="full_text")
        assert early.status_code == 409
        full_text = f"/projects/{t.pid}/screening/queue?stage=full_text"
        assert await _ids(t.reviewer, full_text) == []

        await decide(t.reviewer, t.pid, record, "include")
        assert await _ids(t.reviewer, full_text) == [str(record)]

        # Full text asks for a reason to exclude by default (guide 8.6).
        refused = await decide(t.reviewer, t.pid, record, "exclude", stage="full_text")
        assert refused.json()["code"] == "reason_required"
        # A maybe at full text is not an answer yet.
        await decide(t.reviewer, t.pid, record, "maybe", stage="full_text")
        detail = (await get(t.owner, f"/projects/{t.pid}/records/{record}")).json()
        assert detail["ft_final"] == "pending"

        reasons = (await get(t.owner, f"/projects/{t.pid}/exclusion-reasons")).json()
        reason = reasons[0]["id"]
        done = await decide(
            t.reviewer, t.pid, record, "exclude", stage="full_text", reason_ids=[reason]
        )
        assert done.status_code == 200
        detail = (await get(t.owner, f"/projects/{t.pid}/records/{record}")).json()
        assert detail["ft_final"] == "excluded"


async def test_the_history_comes_a_page_at_a_time(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=3) as t:
        for record in t.records:
            await decide(t.reviewer, t.pid, record, "include")
        first = (await get(t.reviewer, f"/projects/{t.pid}/my-history?limit=2")).json()
        assert len(first["items"]) == 2
        assert first["next_cursor"]
        rest = (
            await get(
                t.reviewer, f"/projects/{t.pid}/my-history?limit=2&cursor={first['next_cursor']}"
            )
        ).json()
        assert rest["next_cursor"] is None
        seen = [item["record_id"] for item in first["items"] + rest["items"]]
        assert sorted(seen) == sorted(str(record) for record in t.records)


async def test_what_is_not_there_or_not_mine_is_refused(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer) as t:
        record = t.records[0]
        nothing = await api(t.reviewer, "DELETE", f"/projects/{t.pid}/records/{record}/decision")
        assert nothing.status_code == 404
        elsewhere = await decide(t.reviewer, t.pid, uuid.uuid4(), "include")
        assert elsewhere.status_code == 404

        note = await post(
            t.owner,
            f"/projects/{t.pid}/records/{record}/notes",
            {"body": "Mine to remove.", "visibility": "team"},
        )
        path = f"/projects/{t.pid}/notes/{note.json()['id']}"
        assert (await api(t.reviewer, "DELETE", path)).status_code == 404
        assert (await api(t.owner, "DELETE", path)).status_code == 204


async def test_conflicts_narrow_to_two_reviewers_and_come_a_page_at_a_time(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=3, third=True) as t:
        assert t.third is not None
        first, second, third = t.records
        # Grace and the owner disagree on the first two; Hedy and the owner on the third.
        await settings(t.owner, t.pid, reviewers_per_record_ta=2)
        for record in (first, second):
            await decide(t.reviewer, t.pid, record, "include")
            await decide(t.owner, t.pid, record, "exclude")
        await decide(t.third, t.pid, third, "include")
        await decide(t.owner, t.pid, third, "exclude")

        base = f"/projects/{t.pid}/conflicts"
        owner, grace = await _me(t.owner), await _me(t.reviewer)
        pair = (await get(t.owner, f"{base}?reviewer_a={grace}&reviewer_b={owner}")).json()
        assert pair["total"] == 2
        assert {item["record_id"] for item in pair["items"]} == {str(first), str(second)}

        page = (await get(t.owner, f"{base}?limit=2")).json()
        assert (page["total"], len(page["items"])) == (3, 2)
        rest = (await get(t.owner, f"{base}?limit=2&cursor={page['next_cursor']}")).json()
        assert [item["record_id"] for item in rest["items"]] == [str(third)]
        assert rest["next_cursor"] is None


async def test_a_bulk_decision_can_be_narrowed_by_status_record_and_stage(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer) as t:
        await settings(t.owner, t.pid, reviewers_per_record_ta=1, maybe_counts_as="maybe")
        maybe, included = t.records[:2]
        await decide(t.reviewer, t.pid, maybe, "maybe")
        await decide(t.reviewer, t.pid, included, "include")
        preview = f"/projects/{t.pid}/bulk-decision/preview"

        body = {"final_decision": "exclude", "expected": 0}
        by_status = await post(t.owner, preview, {**body, "status": "maybe"})
        assert by_status.json() == {"decided": 1}
        by_record = await post(t.owner, preview, {**body, "record_ids": [str(t.records[3])]})
        assert by_record.json() == {"decided": 1}
        full_text = await post(t.owner, preview, {**body, "stage": "full_text"})
        assert full_text.json() == {"decided": 1}

        # Nothing matching is not an error: nothing is decided.
        none = await post(
            t.owner,
            f"/projects/{t.pid}/bulk-decision",
            {**body, "q": "type:editorial"},
        )
        assert none.json() == {"decided": 0}

        done = await post(
            t.owner, f"/projects/{t.pid}/bulk-decision", {**body, "status": "maybe", "expected": 1}
        )
        assert done.json() == {"decided": 1}
        assert await status_of(t.owner, t.pid, maybe) == "excluded"
