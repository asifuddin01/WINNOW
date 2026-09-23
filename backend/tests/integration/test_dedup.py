"""Deduplication end to end: find, review, merge, ignore, auto-resolve (guide 8.4, 9.1).

These run the real pipeline — records in PostgreSQL, the trigram block the database owns,
the pure algorithm, and the cluster tables — rather than the algorithm on its own, which
`tests/unit/dedup` already covers.
"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ClusterStatus, DupCluster, DupClusterMember, Record
from app.models.base import uuid7
from app.workers.dedup import run_dedup
from tests.conftest import MemoryMailer
from tests.project_helpers import OWNER, api, create_project, get, person, post

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "dedup" / "known_records.json"


async def add_records(db: AsyncSession, pid: uuid.UUID, rows: list[dict[str, Any]]) -> None:
    """Put records straight in, the way an import would have."""
    now = datetime.now(UTC)
    db.add_all(
        Record(
            id=uuid.UUID(row["id"]) if row.get("id") else uuid7(),
            project_id=pid,
            title=row["title"],
            title_norm=row.get("title_norm") or (row["title"] or "").lower(),
            abstract=row.get("abstract"),
            authors=row.get("authors", []),
            year=row.get("year"),
            journal=row.get("journal"),
            volume=row.get("volume"),
            issue=row.get("issue"),
            pages=row.get("pages"),
            doi=row.get("doi_norm"),
            doi_norm=row.get("doi_norm"),
            pmid=row.get("pmid"),
            created_at=_when(row.get("imported_at")) or now,
            updated_at=now,
        )
        for row in rows
    )
    await db.flush()


def _when(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


async def manual_only(client: Any, pid: str) -> None:
    """Turn off automatic merging, so a test can see what the algorithm proposed."""
    await api(client, "PATCH", f"/projects/{pid}", {"settings": {"dedup_auto_resolve": False}})


async def dedup(db_app: FastAPI, pid: str) -> Any:
    return await run_dedup(
        sessionmaker=db_app.state.sessionmaker,
        redis=db_app.state.redis,
        project_id=uuid.UUID(pid),
    )


async def clusters_of(db: AsyncSession, pid: str, status: ClusterStatus) -> list[DupCluster]:
    return list(
        await db.scalars(
            select(DupCluster).where(
                DupCluster.project_id == uuid.UUID(pid), DupCluster.status == status
            )
        )
    )


async def test_the_same_paper_from_two_databases_is_found_and_merged(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    """The everyday case: PubMed and Scopus both have it, with the same DOI."""
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        pid = project["id"]
        await add_records(
            db,
            uuid.UUID(pid),
            [
                {
                    "title": "Rotating night shifts and sleep quality in nurses",
                    "title_norm": "rotating night shifts and sleep quality in nurses",
                    "authors": ["Smith, Jane A", "Chowdhury, Sara"],
                    "year": 2019,
                    "journal": "Journal of Advanced Nursing",
                    "doi_norm": "10.1111/jan.13894",
                    "abstract": "AIM: to examine whether rotating night shifts affect sleep.",
                },
                {
                    "title": "ROTATING NIGHT SHIFTS AND SLEEP QUALITY IN NURSES.",
                    "title_norm": "rotating night shifts and sleep quality in nurses",
                    "authors": ["Smith, J."],
                    "year": 2019,
                    "journal": "J Adv Nurs",
                    "doi_norm": "10.1111/jan.13894",
                },
                {
                    "title": "Melatonin for shift work sleep disorder",
                    "title_norm": "melatonin for shift work sleep disorder",
                    "authors": ["Okonkwo, Chidi"],
                    "year": 2021,
                    "doi_norm": "10.1002/xyz.55",
                },
            ],
        )

        result = await dedup(db_app, pid)
        assert result.records == 3
        # Exact DOI: Winnow is certain, so it merges without asking (guide 9.1 step 6).
        assert result.auto_resolved == 1
        assert result.duplicates == 1
        await db.commit()

        summary = (await get(owner, f"/projects/{pid}/dedup/summary")).json()
        assert summary == {
            "pending": 0,
            "certain": 0,
            "resolved": 1,
            "ignored": 0,
            "duplicates": 1,
        }
        # The merged record is kept, flagged and pointed at its primary (guide 8.4).
        merged = list(
            await db.scalars(
                select(Record).where(
                    Record.project_id == uuid.UUID(pid), Record.is_duplicate.is_(True)
                )
            )
        )
        assert len(merged) == 1
        assert merged[0].duplicate_of is not None
        assert merged[0].journal == "J Adv Nurs"  # nothing about it was rewritten


async def test_a_title_that_blocking_cannot_see_is_found_by_the_database(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    """Block C (guide 9.1): the same words in a different order, so blocks A and B miss it."""
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        pid = project["id"]
        await add_records(
            db,
            uuid.UUID(pid),
            [
                {
                    "title": "A prospective cohort study of night shifts and sleep in nurses",
                    "title_norm": "a prospective cohort study of night shifts and sleep in nurses",
                    "authors": ["Rahman, Imran"],
                    "year": 2020,
                    "journal": "Sleep Medicine",
                },
                {
                    "title": "Night shifts and sleep in nurses: a prospective cohort study",
                    "title_norm": "night shifts and sleep in nurses a prospective cohort study",
                    "authors": ["Rahman, I"],
                    "year": 2020,
                    "journal": "Sleep Medicine",
                },
            ],
        )
        await db.commit()
        await manual_only(owner, pid)

        result = await dedup(db_app, pid)
        assert result.clusters == 1, "the trigram block should pair the reordered title"
        pending = (await get(owner, f"/projects/{pid}/dedup/clusters")).json()
        assert len(pending) == 1
        assert {member["title"] for member in pending[0]["members"]} == {
            "A prospective cohort study of night shifts and sleep in nurses",
            "Night shifts and sleep in nurses: a prospective cohort study",
        }
        assert pending[0]["score"] >= 0.9


async def test_a_reviewer_keeps_the_copy_they_choose(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        pid = project["id"]
        await add_records(
            db,
            uuid.UUID(pid),
            [
                {
                    "title": "Sleep quality and patient safety incidents",
                    "title_norm": "sleep quality and patient safety incidents",
                    "authors": ["Novak, Petra"],
                    "year": 2022,
                    "journal": "BMJ Open",
                    "abstract": "The fuller record, which Winnow would keep.",
                },
                {
                    "title": "Sleep quality and patient safety incidents.",
                    "title_norm": "sleep quality and patient safety incidents",
                    "authors": ["Novak, P"],
                    "year": 2022,
                    "journal": "BMJ Open",
                },
            ],
        )
        await db.commit()
        await manual_only(owner, pid)
        await dedup(db_app, pid)

        cluster = (await get(owner, f"/projects/{pid}/dedup/clusters")).json()[0]
        suggested = next(member for member in cluster["members"] if member["is_primary"])
        other = next(member for member in cluster["members"] if not member["is_primary"])
        assert suggested["abstract"], "the fuller record is suggested (guide 9.1 step 5)"

        # The reviewer disagrees and keeps the other one.
        merge = await post(
            owner,
            f"/projects/{pid}/dedup/clusters/{cluster['id']}/merge",
            {"primary_id": other["id"]},
        )
        assert merge.status_code == 200
        assert merge.json()["merged"] == 1
        kept = await db.get(Record, uuid.UUID(other["id"]))
        gone = await db.get(Record, uuid.UUID(suggested["id"]))
        await db.refresh(kept)
        await db.refresh(gone)
        assert kept is not None
        assert kept.is_duplicate is False
        assert gone is not None
        assert gone.is_duplicate is True
        assert gone.duplicate_of == kept.id
        # And a second decision is refused rather than applied twice.
        again = await post(
            owner,
            f"/projects/{pid}/dedup/clusters/{cluster['id']}/merge",
            {"primary_id": other["id"]},
        )
        assert again.status_code == 409


async def test_not_duplicates_is_remembered_when_dedup_runs_again(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    """An erratum and its original share a title; someone says so once, not every run."""
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        pid = project["id"]
        await add_records(
            db,
            uuid.UUID(pid),
            [
                {
                    "title": "Shift work and sleep: a randomised trial",
                    "title_norm": "shift work and sleep a randomised trial",
                    "authors": ["Lund, Christina"],
                    "year": 2018,
                    "journal": "Chronobiology International",
                },
                {
                    "title": "Shift work and sleep: a randomised trial [Erratum]",
                    "title_norm": "shift work and sleep a randomised trial erratum",
                    "authors": ["Lund, Christina"],
                    "year": 2018,
                    "journal": "Chronobiology International",
                },
            ],
        )
        await db.commit()
        await manual_only(owner, pid)
        await dedup(db_app, pid)

        cluster = (await get(owner, f"/projects/{pid}/dedup/clusters")).json()[0]
        ignored = await post(owner, f"/projects/{pid}/dedup/clusters/{cluster['id']}/ignore", {})
        assert ignored.status_code == 200
        assert ignored.json()["status"] == "ignored"

        await dedup(db_app, pid)
        assert (await get(owner, f"/projects/{pid}/dedup/clusters")).json() == []
        assert len(await clusters_of(db, pid, ClusterStatus.IGNORED)) == 1
        # Neither record was touched.
        live = await db.scalar(
            select(func.count())
            .select_from(Record)
            .where(Record.project_id == uuid.UUID(pid), Record.is_duplicate.is_(False))
        )
        assert live == 2


async def test_auto_resolve_merges_the_certain_ones_in_one_go(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        pid = project["id"]
        # Auto-resolve off, so everything waits for the bulk action.
        await manual_only(owner, pid)
        pairs: list[dict[str, Any]] = []
        for index in range(4):
            title = f"Deep learning for kidney segmentation, part {index}"
            for copy in range(2):
                pairs.append(
                    {
                        "title": title if copy == 0 else title.upper(),
                        "title_norm": title.lower(),
                        "authors": ["Myronenko, Andriy"],
                        "year": 2019,
                        "journal": "Medical Image Analysis",
                        "doi_norm": f"10.1016/j.media.{index}",
                    }
                )
        await add_records(db, uuid.UUID(pid), pairs)
        await db.commit()

        await dedup(db_app, pid)
        assert len(await clusters_of(db, pid, ClusterStatus.PENDING)) == 4

        resolved = await post(owner, f"/projects/{pid}/dedup/auto-resolve", {"min_score": 0.98})
        assert resolved.status_code == 200
        assert resolved.json() == {
            "cluster_id": None,
            "primary_id": None,
            "merged": 4,
            "clusters": 4,
        }
        summary = (await get(owner, f"/projects/{pid}/dedup/summary")).json()
        assert summary["duplicates"] == 4
        assert summary["pending"] == 0


async def test_records_merged_as_duplicates_leave_the_screening_list(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    """Guide 9.4: what is screened is the non-duplicate records."""
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        pid = project["id"]
        await add_records(
            db,
            uuid.UUID(pid),
            [
                {
                    "title": "Hydronephrosis on CT: a review",
                    "title_norm": "hydronephrosis on ct a review",
                    "year": 2020,
                    "doi_norm": "10.1000/hydro.1",
                },
                {
                    "title": "Hydronephrosis on CT: a review",
                    "title_norm": "hydronephrosis on ct a review",
                    "year": 2020,
                    "doi_norm": "10.1000/hydro.1",
                },
            ],
        )
        await db.commit()
        await dedup(db_app, pid)

        page = (await get(owner, f"/projects/{pid}/records")).json()
        assert page["total"] == 1, "the merged copy is out of the list by default"
        with_duplicates = (await get(owner, f"/projects/{pid}/records?duplicates=true")).json()
        assert with_duplicates["total"] == 2


async def test_only_admins_run_or_resolve_deduplication(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    """Guide 7: running dedup sits with importing; anyone may look at the result."""
    from tests.project_helpers import REVIEWER, add_member

    async with (
        person(db_app, mailer, OWNER, ip="10.7.0.1") as owner,
        person(db_app, mailer, REVIEWER, ip="10.7.0.2") as reviewer,
    ):
        project = await create_project(owner)
        pid = project["id"]
        await add_member(owner, reviewer, pid, REVIEWER)
        await add_records(
            db,
            uuid.UUID(pid),
            [
                {
                    "title": "Urolithiasis detection on low-dose CT",
                    "title_norm": "urolithiasis detection on low dose ct",
                    "year": 2021,
                },
                {
                    "title": "Urolithiasis detection on low-dose CT",
                    "title_norm": "urolithiasis detection on low dose ct",
                    "year": 2021,
                },
            ],
        )
        await db.commit()
        await manual_only(owner, pid)
        await dedup(db_app, pid)
        cluster = (await get(owner, f"/projects/{pid}/dedup/clusters")).json()[0]

        assert (await post(reviewer, f"/projects/{pid}/dedup/run", {})).status_code == 403
        merge = await post(
            reviewer,
            f"/projects/{pid}/dedup/clusters/{cluster['id']}/merge",
            {"primary_id": cluster["members"][0]["id"]},
        )
        assert merge.status_code == 403
        assert (await post(reviewer, f"/projects/{pid}/dedup/auto-resolve", {})).status_code == 403
        # But a reviewer can see what is waiting.
        assert (await get(reviewer, f"/projects/{pid}/dedup/clusters")).status_code == 200


async def test_merging_a_record_that_is_not_in_the_group_is_refused(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        pid = project["id"]
        await add_records(
            db,
            uuid.UUID(pid),
            [
                {
                    "title": "Kidney tumour segmentation challenge",
                    "title_norm": "kidney tumour segmentation challenge",
                    "year": 2019,
                },
                {
                    "title": "Kidney tumour segmentation challenge",
                    "title_norm": "kidney tumour segmentation challenge",
                    "year": 2019,
                },
            ],
        )
        await db.commit()
        await manual_only(owner, pid)
        await dedup(db_app, pid)
        cluster = (await get(owner, f"/projects/{pid}/dedup/clusters")).json()[0]

        refused = await post(
            owner,
            f"/projects/{pid}/dedup/clusters/{cluster['id']}/merge",
            {"primary_id": str(uuid.uuid4())},
        )
        assert refused.status_code == 422
        assert refused.json()["code"] == "not_in_cluster"


async def test_the_known_duplicates_fixture_meets_the_acceptance_bar(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    """Phase 4 acceptance: at least 97% precision and 95% recall on known duplicates.

    The fixture is deliberately awkward — an erratum against its original, a conference
    abstract against the full article, accents, HTML and missing years — and it runs here
    through the database, so the trigram block is part of what is measured.
    """
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        pid = project["id"]
        by_key = {row["key"]: uuid.UUID(row["id"]) for row in payload["records"]}
        await add_records(db, uuid.UUID(pid), payload["records"])
        await db.commit()

        # Nothing merges itself: the measurement is of what the algorithm proposed.
        await manual_only(owner, pid)
        await dedup(db_app, pid)

        truth: set[frozenset[uuid.UUID]] = set()
        for group in payload["truth"]["duplicate_groups"]:
            ids = [by_key[key] for key in group["members"]]
            truth.update(frozenset(pair) for pair in _pairs(ids))

        found: set[frozenset[uuid.UUID]] = set()
        for row in await clusters_of(db, pid, ClusterStatus.PENDING):
            members = list(
                await db.scalars(
                    select(DupClusterMember.record_id).where(DupClusterMember.cluster_id == row.id)
                )
            )
            found.update(frozenset(pair) for pair in _pairs(members))

        true_positives = len(found & truth)
        precision = true_positives / len(found) if found else 1.0
        recall = true_positives / len(truth) if truth else 1.0
        assert precision >= 0.97, f"precision {precision:.2%}: {found - truth}"
        assert recall >= 0.95, f"recall {recall:.2%}: {truth - found}"

        # The pairs the fixture says must never be joined, are not.
        for group in payload["truth"]["must_not_cluster"]:
            pair = frozenset(by_key[key] for key in group["members"])
            assert pair not in found, group["name"]


def _pairs(ids: list[uuid.UUID]) -> list[tuple[uuid.UUID, uuid.UUID]]:
    return [(left, right) for index, left in enumerate(ids) for right in ids[index + 1 :]]
