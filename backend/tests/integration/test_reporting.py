"""PRISMA 2020 counts and screening statistics against a hand-calculated review
(guide 8.14, 8.15, 9.3, 9.4; Phase 8 acceptance: "PRISMA numbers match a hand-calculated
fixture; kappa matches a reference implementation")."""

import uuid
from datetime import date
from typing import Any

from fastapi import FastAPI
from sklearn.metrics import cohen_kappa_score
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ConflictResolution,
    Decision,
    DecisionValue,
    ExclusionReason,
    FileFormat,
    FinalDecision,
    FullTextStatus,
    ImportBatch,
    ImportStatus,
    Record,
    ResolutionSource,
    ScreeningStage,
    TitleAbstractStatus,
    User,
)
from app.models.base import uuid7
from tests.conftest import MemoryMailer
from tests.project_helpers import OWNER, REVIEWER, add_member, api, get, person, post
from tests.screening_helpers import THIRD, add_records, decide, settings, team


async def batch(
    db: AsyncSession, pid: str, database: str, imported: int, status: ImportStatus
) -> None:
    db.add(
        ImportBatch(
            id=uuid7(),
            project_id=uuid.UUID(pid),
            source_name=database,
            database_name=database,
            file_key=f"imports/{uuid.uuid4().hex}",
            filename="search.ris",
            size_bytes=1,
            file_format=FileFormat.RIS,
            status=status,
            total=imported,
            imported=imported,
        )
    )


async def set_status(
    db: AsyncSession,
    ids: list[uuid.UUID],
    *,
    ta: TitleAbstractStatus,
    ft: FullTextStatus | None = None,
) -> None:
    values: dict[str, Any] = {"ta_final": ta}
    if ft is not None:
        values["ft_final"] = ft
    await db.execute(update(Record).where(Record.id.in_(ids)).values(**values))


async def test_prisma_matches_a_hand_calculated_review(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    """
    Identification: PubMed 20 + "pubmed " 5 (one database, typed twice) = 25, Embase 15, a
    failed Scopus import of 99 that must not count: 40 from databases; citation searching
    12 and websites 3 by hand: 55 identified. 8 of the 40 records are duplicates; 5
    removed for other reasons by hand.
    Screening: 32 screened; 18 excluded, 10 included, 3 pending and 1 in conflict at title
    and abstract (so 4 awaiting). One excluded record still carries a full-text exclusion
    from before it was excluded: it must not count.
    Full text, of the 10 sought: 2 not retrieved, so 8 assessed; 4 excluded, 3 included,
    1 pending. The 4 exclusions, one reason each: wrong population (a reviewer gave it
    beside wrong outcome; population comes first in the review's list), wrong study
    design, wrong outcome (a resolution's reason wins over the reviewers'), and one with
    no reason given.
    """
    async with team(db_app, db, mailer, records=40) as t:
        pid = uuid.UUID(t.pid)
        await batch(db, t.pid, "PubMed", 20, ImportStatus.DONE)
        await batch(db, t.pid, "pubmed ", 5, ImportStatus.DONE)
        await batch(db, t.pid, "Embase", 15, ImportStatus.DONE)
        await batch(db, t.pid, "Scopus", 99, ImportStatus.FAILED)
        duplicates, live = t.records[:8], t.records[8:]
        await db.execute(
            update(Record)
            .where(Record.id.in_(duplicates))
            .values(is_duplicate=True, duplicate_of=live[0])
        )
        ta_excluded, ta_included = live[:18], live[18:28]
        ta_pending, ta_conflict = live[28:31], live[31:32]
        await set_status(db, ta_excluded, ta=TitleAbstractStatus.EXCLUDED)
        await set_status(
            db, ta_excluded[:1], ta=TitleAbstractStatus.EXCLUDED, ft=FullTextStatus.EXCLUDED
        )
        await set_status(db, ta_pending, ta=TitleAbstractStatus.PENDING)
        await set_status(db, ta_conflict, ta=TitleAbstractStatus.CONFLICT)
        ft_excluded = ta_included[:4]
        await set_status(
            db, ft_excluded, ta=TitleAbstractStatus.INCLUDED, ft=FullTextStatus.EXCLUDED
        )
        await set_status(
            db, ta_included[4:7], ta=TitleAbstractStatus.INCLUDED, ft=FullTextStatus.INCLUDED
        )
        await set_status(
            db, ta_included[7:9], ta=TitleAbstractStatus.INCLUDED, ft=FullTextStatus.NOT_RETRIEVABLE
        )
        await set_status(
            db, ta_included[9:], ta=TitleAbstractStatus.INCLUDED, ft=FullTextStatus.PENDING
        )

        reasons = {
            str(reason.label): reason.id
            for reason in await db.scalars(
                select(ExclusionReason).where(ExclusionReason.project_id == pid)
            )
        }
        owner = await db.scalar(select(User.id).where(User.email == OWNER))
        reviewer = await db.scalar(select(User.id).where(User.email == REVIEWER))
        assert owner is not None
        assert reviewer is not None

        def excluded(record_id: uuid.UUID, user_id: uuid.UUID, *labels: str) -> Decision:
            return Decision(
                id=uuid7(),
                project_id=pid,
                record_id=record_id,
                user_id=user_id,
                stage=ScreeningStage.FULL_TEXT,
                decision=DecisionValue.EXCLUDE,
                reason_ids=[reasons[label] for label in labels],
            )

        db.add_all(
            [
                excluded(ft_excluded[0], owner, "Wrong outcome", "Wrong population"),
                excluded(ft_excluded[0], reviewer, "Wrong outcome"),
                excluded(ft_excluded[1], owner, "Wrong study design"),
                excluded(ft_excluded[2], owner, "Wrong population"),
                excluded(ft_excluded[3], owner),
                ConflictResolution(
                    id=uuid7(),
                    project_id=pid,
                    record_id=ft_excluded[2],
                    stage=ScreeningStage.FULL_TEXT,
                    resolved_by=owner,
                    final_decision=FinalDecision.EXCLUDE,
                    reason_ids=[reasons["Wrong outcome"]],
                    source=ResolutionSource.CONFLICT,
                ),
            ]
        )
        await db.commit()
        manual = await api(
            t.owner,
            "PATCH",
            f"/projects/{t.pid}/prisma/manual",
            {
                "other_sources": [
                    {"name": "Citation searching", "count": 12},
                    {"name": "Websites", "count": 3},
                ],
                "removed_other_reasons": 5,
            },
        )
        assert manual.status_code == 200, manual.text

        flow = (await get(t.reviewer, f"/projects/{t.pid}/prisma")).json()
        assert flow["database_sources"] == [
            {"name": "PubMed", "count": 25},
            {"name": "Embase", "count": 15},
        ]
        assert flow["other_sources"] == [
            {"name": "Citation searching", "count": 12},
            {"name": "Websites", "count": 3},
        ]
        assert {key: value for key, value in flow.items() if isinstance(value, int)} == {
            "records_identified": 55,
            "duplicates_removed": 8,
            "records_removed_other_reasons": 5,
            "records_screened": 32,
            "records_excluded": 18,
            "reports_sought": 10,
            "reports_not_retrieved": 2,
            "reports_assessed": 8,
            "reports_excluded_total": 4,
            "studies_included": 3,
            "awaiting_title_abstract": 4,
            "awaiting_full_text": 1,
        }
        assert flow["reports_excluded"] == [
            {"reason": "Wrong population", "count": 1},
            {"reason": "Wrong outcome", "count": 1},
            {"reason": "Wrong study design", "count": 1},
            {"reason": "Reason not recorded", "count": 1},
        ]


async def test_the_diagram_downloads_as_svg_png_and_pdf(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=3) as t:
        await batch(db, t.pid, "MEDLINE", 3, ImportStatus.DONE)
        await db.commit()
        base = f"/api/v1/projects/{t.pid}/prisma"
        svg = await t.reviewer.get(f"{base}.svg")
        assert svg.status_code == 200
        assert svg.headers["content-type"] == "image/svg+xml"
        assert svg.headers["content-disposition"] == 'attachment; filename="prisma-2020.svg"'
        assert svg.headers["x-content-type-options"] == "nosniff"
        assert "<script" not in svg.text
        assert "MEDLINE" in svg.text
        shown = await t.reviewer.get(f"{base}.svg", params={"inline": "true"})
        assert shown.headers["content-disposition"].startswith("inline;")
        png = await t.reviewer.get(f"{base}.png")
        assert png.content.startswith(b"\x89PNG\r\n\x1a\n")
        # 300 dpi, said in the file: the pHYs chunk right after the header, 11,811 pixels
        # per metre both ways.
        assert png.content[33:41] == b"\x00\x00\x00\tpHYs"
        assert png.content[41:50] == (11811).to_bytes(4, "big") * 2 + b"\x01"
        pdf = await t.reviewer.get(f"{base}.pdf")
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.content.startswith(b"%PDF-")
        assert (await t.reviewer.get(f"{base}.gif")).status_code in (404, 422)


async def test_manual_counts_are_checked_and_only_owners_and_admins_set_them(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=3) as t:
        await batch(db, t.pid, "MEDLINE", 3, ImportStatus.DONE)
        await db.commit()
        path = f"/projects/{t.pid}/prisma/manual"
        twice = await api(
            t.owner,
            "PATCH",
            path,
            {
                "other_sources": [
                    {"name": "Websites", "count": 1},
                    {"name": " websites", "count": 2},
                ]
            },
        )
        assert twice.status_code == 409
        # More removed before screening than were ever identified: refused, and not kept.
        impossible = await api(t.owner, "PATCH", path, {"removed_other_reasons": 50})
        assert impossible.status_code == 422
        assert impossible.json()["code"] == "prisma_inconsistent"
        assert (await get(t.owner, f"/projects/{t.pid}/prisma")).json()["manual"][
            "removed_other_reasons"
        ] == 0
        assert (
            await api(t.reviewer, "PATCH", path, {"removed_other_reasons": 1})
        ).status_code == 403


async def test_agreement_matches_scikit_learns_cohens_kappa(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    """Two reviewers on the same 12 records: Winnow's kappa is the reference implementation's."""
    ada = ["include"] * 5 + ["exclude"] * 5 + ["maybe", "include"]
    grace = ["include"] * 3 + ["exclude"] * 2 + ["exclude"] * 4 + ["include", "maybe", "exclude"]
    async with team(db_app, db, mailer, records=12) as t:
        await settings(t.owner, t.pid, maybe_counts_as="maybe")
        for record_id, a, b in zip(t.records, ada, grace, strict=True):
            assert (await decide(t.owner, t.pid, record_id, a)).status_code == 200
            assert (await decide(t.reviewer, t.pid, record_id, b)).status_code == 200
        body = (await get(t.owner, f"/projects/{t.pid}/stats")).json()
        [ta, ft] = body["stages"]
        assert ta["stage"] == "title_abstract"
        # Both included three records: those reached full text.
        assert ft["records"] == 3
        [pair] = ta["agreement"]["pairs"]
        assert pair["records"] == 12
        expected = cohen_kappa_score(ada, grace)
        assert abs(pair["kappa"] - expected) < 1e-9
        assert pair["percent"] == sum(a == b for a, b in zip(ada, grace, strict=True)) / 12
        assert pair["band"] is not None
        # The owner asked: their own row is marked (every test account has the same name).
        [mine] = [row for row in ta["reviewers"] if row["mine"]]
        assert (mine["decided"], mine["included"], mine["excluded"], mine["maybe"]) == (12, 6, 5, 1)
        assert len(ta["reviewers"]) == 2
        assert body["blind"] is False
        assert sum(day["decisions"] for day in ta["per_day"]) == 24


async def test_fleiss_kappa_for_three_reviewers_per_record(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    """Checked against the formula written out independently of app.stats."""
    ratings = [
        ("include", "include", "include"),
        ("include", "include", "exclude"),
        ("exclude", "exclude", "exclude"),
        ("exclude", "include", "exclude"),
        ("include", "include", "include"),
        ("exclude", "exclude", "exclude"),
    ]
    async with team(db_app, db, mailer, records=6, third=True) as t:
        assert t.third is not None
        await settings(t.owner, t.pid, reviewers_per_record_ta=3)
        for record_id, votes in zip(t.records, ratings, strict=True):
            for client, vote in zip((t.owner, t.reviewer, t.third), votes, strict=True):
                decided = await decide(client, t.pid, record_id, vote)
                assert decided.status_code == 200, decided.text
        agreement = (await get(t.owner, f"/projects/{t.pid}/stats")).json()["stages"][0][
            "agreement"
        ]
        n, k = len(ratings), 3
        counts = [(votes.count("include"), votes.count("exclude")) for votes in ratings]
        p_i = [(a * a + b * b - k) / (k * (k - 1)) for a, b in counts]
        p_bar = sum(p_i) / n
        p_include = sum(a for a, _ in counts) / (n * k)
        p_e = p_include**2 + (1 - p_include) ** 2
        assert abs(agreement["fleiss_kappa"] - (p_bar - p_e) / (1 - p_e)) < 1e-9
        assert agreement["fleiss_records"] == 6
        assert agreement["raters"] == 3
        assert len(agreement["pairs"]) == 3


async def test_a_blinded_reviewer_sees_only_their_own_numbers(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=4) as t:
        await settings(t.owner, t.pid, blind_mode=True)
        for record_id in t.records:
            await decide(t.owner, t.pid, record_id, "include")
            await decide(t.reviewer, t.pid, record_id, "exclude")
        body = (await get(t.reviewer, f"/projects/{t.pid}/stats")).json()
        assert body["blind"] is True
        ta = body["stages"][0]
        assert [row["mine"] for row in ta["reviewers"]] == [True]
        assert ta["agreement"] is None
        assert ta["conflicts"] is None
        assert sum(day["decisions"] for day in ta["per_day"]) == 4


async def test_viewers_may_read_the_prisma_flow(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with (
        person(db_app, mailer, OWNER, ip="10.8.0.1") as owner,
        person(db_app, mailer, THIRD, ip="10.8.0.3") as viewer,
    ):
        from tests.project_helpers import create_project

        pid = (await create_project(owner))["id"]
        await add_records(db, pid, 2)
        await batch(db, pid, "MEDLINE", 2, ImportStatus.DONE)
        await db.commit()
        await add_member(owner, viewer, pid, THIRD, role="viewer")
        flow = await get(viewer, f"/projects/{pid}/prisma")
        assert flow.status_code == 200
        assert flow.json()["records_screened"] == 2


async def test_the_methods_text_describes_the_review_with_its_numbers(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=4) as t:
        await settings(t.owner, t.pid, reviewers_per_record_ta=2)
        await batch(db, t.pid, "PubMed", 4, ImportStatus.DONE)
        await db.execute(
            update(ImportBatch)
            .where(ImportBatch.project_id == uuid.UUID(t.pid))
            .values(search_date=date(2026, 3, 3))
        )
        await db.commit()
        # Three agreements and one disagreement in four: 75%, kappa (0.75 - 0.5) / 0.5.
        for record, mine, theirs in zip(
            t.records,
            ["include", "include", "exclude", "include"],
            ["include", "include", "exclude", "exclude"],
            strict=True,
        ):
            await decide(t.owner, t.pid, record, mine)
            await decide(t.reviewer, t.pid, record, theirs)
        resolved = await post(
            t.owner,
            f"/projects/{t.pid}/conflicts/{t.records[3]}/resolve",
            {"final_decision": "include"},
        )
        assert resolved.status_code == 200, resolved.text

        methods = (await get(t.owner, f"/projects/{t.pid}/methods-text")).json()
        assert methods["complete"] is False  # full texts still wait
        assert methods["blind"] is False
        first, second = methods["text"].split("\n\n")
        assert first == (
            "We searched PubMed (4 records, searched 3 March 2026). Two reviewers "
            "independently screened the titles and abstracts of 4 records, blinded to each "
            "other's decisions; agreement was 75.0% (Cohen's κ = 0.50, moderate). "
            "Disagreements at title and abstract (1) were resolved by discussion (1)."
        )
        assert second.startswith("We sought 3 full-text reports.")

        # A blinded reviewer's text leaves out what the team did together.
        theirs = (await get(t.reviewer, f"/projects/{t.pid}/methods-text")).json()
        assert theirs["blind"] is True
        assert "κ" not in theirs["text"]
        assert "Disagreements" not in theirs["text"]
        assert theirs["text"].startswith("We searched PubMed (4 records")
