"""Risk of bias (guide 8.13): assessing included studies with the built-in tools, blinding,
choosing the final assessment, and the traffic-light and summary plots."""

import uuid
from typing import Any

from defusedxml import ElementTree
from fastapi import FastAPI
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FullTextStatus, Record, TitleAbstractStatus
from app.plots.rob import TIMES
from tests.conftest import MemoryMailer
from tests.project_helpers import api, delete, get, post
from tests.screening_helpers import settings, team

RANDOMISATION = "randomisation_process"
DOMAINS = [
    "randomisation_process",
    "deviations_from_intended_interventions",
    "missing_outcome_data",
    "measurement_of_outcome",
    "selection_of_reported_result",
]


def rob2(*judgements: str, status: str = "submitted", overall: str | None = None) -> dict[str, Any]:
    return {
        "tool_key": "rob2",
        "variant_key": "parallel_assignment",
        "judgements": {
            domain: {"risk_of_bias": judgement}
            for domain, judgement in zip(DOMAINS, judgements, strict=False)
        },
        "answers": {RANDOMISATION: {"random_sequence": "yes"}} if judgements else {},
        "support": {RANDOMISATION: "Computer-generated sequence."},
        "overall": overall,
        "status": status,
    }


async def included(db: AsyncSession, ids: list[uuid.UUID], **fields: Any) -> None:
    await db.execute(
        update(Record)
        .where(Record.id.in_(ids))
        .values(ta_final=TitleAbstractStatus.INCLUDED, ft_final=FullTextStatus.INCLUDED, **fields)
    )
    await db.commit()


async def test_the_four_tools_are_offered_with_their_domains(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=1) as t:
        tools = (await get(t.reviewer, f"/projects/{t.pid}/rob/tools")).json()
        assert {tool["key"] for tool in tools} == {"rob2", "robins_i", "nos", "quadas2"}
        rob2_tool = next(tool for tool in tools if tool["key"] == "rob2")
        assert [d["key"] for d in rob2_tool["variants"][0]["domains"]] == DOMAINS
        quadas = next(tool for tool in tools if tool["key"] == "quadas2")
        assert [a["key"] for a in quadas["variants"][0]["domains"][0]["axes"]] == [
            "risk_of_bias",
            "applicability",
        ]


async def test_an_assessment_fits_its_tool_and_is_complete_when_submitted(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=2) as t:
        study, other = t.records
        path = f"/projects/{t.pid}/rob/{study}"
        # Only studies included at full text are assessed.
        early = await api(t.reviewer, "PUT", path, rob2("low"))
        assert early.status_code == 409
        await included(db, [study])

        draft = await api(t.reviewer, "PUT", path, rob2("low", status="draft"))
        assert draft.status_code == 200, draft.text
        assert draft.json()["status"] == "draft"
        assert draft.json()["tool_version"] == "22 August 2019"

        incomplete = await api(t.reviewer, "PUT", path, rob2("low"))
        assert incomplete.status_code == 422
        assert "needs a judgement" in incomplete.json()["detail"]
        wrong = await api(t.reviewer, "PUT", path, rob2("low", "serious", "low", "low", "low"))
        assert wrong.status_code == 422
        assert "'serious' is not a judgement" in wrong.json()["detail"]
        stranger = {**rob2(*["low"] * 5), "judgements": {"made_up": {"risk_of_bias": "low"}}}
        assert (await api(t.reviewer, "PUT", path, stranger)).status_code == 422
        unknown_tool = await api(t.reviewer, "PUT", path, {**rob2("low"), "tool_key": "cochrane_1"})
        assert unknown_tool.status_code == 404

        done = await api(t.reviewer, "PUT", path, rob2(*["low"] * 4, "high", overall="high"))
        assert done.status_code == 200, done.text
        assert done.json()["status"] == "submitted"
        mine = (await get(t.reviewer, path)).json()
        assert [a["id"] for a in mine["assessments"]] == [draft.json()["id"]]  # one per tool
        assert mine["assessments"][0]["judgements"][DOMAINS[4]] == {"risk_of_bias": "high"}

        removed = await delete(t.reviewer, f"/projects/{t.pid}/rob/{study}?tool=rob2")
        assert removed.status_code == 204
        assert (await get(t.reviewer, path)).json()["assessments"] == []
        assert (await get(t.reviewer, f"/projects/{t.pid}/rob/{other}")).status_code == 409


async def test_assessments_are_blinded_and_one_is_chosen_final(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=3) as t:
        single, double, draft_only = t.records
        await included(db, t.records, authors=["Smith, Jane"], year=2019)
        await settings(t.owner, t.pid, blind_mode=True)
        base = f"/projects/{t.pid}/rob"
        await api(t.reviewer, "PUT", f"{base}/{single}", rob2(*["low"] * 5, overall="low"))
        await api(t.reviewer, "PUT", f"{base}/{double}", rob2(*["some_concerns"] * 5))
        theirs = await api(t.owner, "PUT", f"{base}/{double}", rob2(*["high"] * 5, overall="high"))
        await api(t.owner, "PUT", f"{base}/{draft_only}", rob2("low", status="draft"))

        # Blind mode: the reviewer sees only their own, and summarises only their own.
        seen = (await get(t.reviewer, f"{base}/{double}")).json()["assessments"]
        assert [a["mine"] for a in seen] == [True]
        own = (await get(t.reviewer, f"{base}/summary?tool=rob2")).json()
        assert own["own_only"] is True
        assert len(own["variants"][0]["studies"]) == 2

        summary = (await get(t.owner, f"{base}/summary?tool=rob2")).json()
        assert summary["own_only"] is False
        assert summary["awaiting_final"] == [str(double)]
        [variant] = summary["variants"]
        assert [s["record_id"] for s in variant["studies"]] == [str(single)]

        # A reviewer without the right to resolve cannot choose; the owner can.
        body = {"assessment_id": theirs.json()["id"]}
        assert (await post(t.reviewer, f"{base}/{double}/final", body)).status_code == 403
        chosen = await post(t.owner, f"{base}/{double}/final", body)
        assert chosen.status_code == 200, chosen.text
        assert chosen.json()["final"] is True
        summary = (await get(t.owner, f"{base}/summary?tool=rob2")).json()
        assert summary["awaiting_final"] == []
        [variant] = summary["variants"]
        assert {s["record_id"] for s in variant["studies"]} == {str(single), str(double)}
        first = variant["domains"][0]
        assert first["domain_key"] == RANDOMISATION
        assert first["total"] == 2
        assert {c["judgement"]: c["count"] for c in first["counts"]} == {
            "low": 1,
            "some_concerns": 0,
            "high": 1,
        }
        # Changing the final assessment makes it no longer final.
        await api(t.owner, "PUT", f"{base}/{double}", rob2(*["low"] * 5))
        again = (await get(t.owner, f"{base}/summary?tool=rob2")).json()
        assert again["awaiting_final"] == [str(double)]


async def test_the_plots_are_safe_accessible_svg_and_png(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=2) as t:
        first, second = t.records
        await included(db, [first], authors=["O'Brien <script>, A"], year=2020)
        await included(db, [second], authors=["Lee, K"], year=2021)
        base = f"/projects/{t.pid}/rob"
        await api(t.reviewer, "PUT", f"{base}/{first}", rob2(*["low"] * 5, overall="low"))
        await api(
            t.reviewer,
            "PUT",
            f"{base}/{second}",
            rob2("high", "low", "some_concerns", "low", "low"),
        )

        light = await t.owner.get(f"/api/v1{base}/summary.svg", params={"tool": "rob2"})
        assert light.status_code == 200
        assert light.headers["content-type"] == "image/svg+xml"
        assert (
            light.headers["content-disposition"] == 'attachment; filename="rob2-traffic-light.svg"'
        )
        tree = ElementTree.fromstring(light.text)
        assert tree.find("{http://www.w3.org/2000/svg}title") is not None
        assert "<script" not in light.text
        assert (
            "O&apos;Brien &lt;script&gt; 2020" in light.text
            or "O'Brien &lt;script&gt; 2020" in light.text
        )
        assert TIMES in light.text  # high carries a symbol, not only a colour
        assert "Lee 2021" in light.text

        bars = await t.owner.get(
            f"/api/v1{base}/summary.svg", params={"tool": "rob2", "plot": "summary"}
        )
        ElementTree.fromstring(bars.text)
        assert "50%" in bars.text
        png = await t.owner.get(
            f"/api/v1{base}/summary.png",
            params={"tool": "rob2", "plot": "summary", "inline": "true"},
        )
        assert png.content.startswith(b"\x89PNG")
        assert png.headers["content-disposition"].startswith("inline;")
        missing = await t.owner.get(
            f"/api/v1{base}/summary.svg", params={"tool": "rob2", "variant": "crossover"}
        )
        assert missing.status_code == 404


async def test_quadas_judges_two_axes_and_nos_counts_stars(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer
) -> None:
    async with team(db_app, db, mailer, records=2) as t:
        diagnostic, cohort = t.records
        await included(db, t.records, authors=["Chen, W"], year=2022)
        base = f"/projects/{t.pid}/rob"
        tools = {tool["key"]: tool for tool in (await get(t.owner, f"{base}/tools")).json()}

        quadas = tools["quadas2"]["variants"][0]
        judgements = {
            domain["key"]: {axis["key"]: "low" for axis in domain["axes"]}
            for domain in quadas["domains"]
        }
        saved = await api(
            t.reviewer,
            "PUT",
            f"{base}/{diagnostic}",
            {
                "tool_key": "quadas2",
                "variant_key": quadas["key"],
                "judgements": judgements,
                "status": "submitted",
            },
        )
        assert saved.status_code == 200, saved.text
        summary = (await get(t.owner, f"{base}/summary?tool=quadas2")).json()
        axes = {(d["domain_key"], d["axis_key"]) for d in summary["variants"][0]["domains"]}
        assert ("patient_selection", "applicability") in axes
        assert ("flow_and_timing", "applicability") not in axes

        nos = next(v for v in tools["nos"]["variants"] if v["key"] == "cohort")
        stars = {
            domain["key"]: {domain["axes"][0]["key"]: domain["axes"][0]["judgements"][-1]["key"]}
            for domain in nos["domains"]
        }
        saved = await api(
            t.reviewer,
            "PUT",
            f"{base}/{cohort}",
            {
                "tool_key": "nos",
                "variant_key": "cohort",
                "judgements": stars,
                "status": "submitted",
            },
        )
        assert saved.status_code == 200, saved.text
        plot = await t.owner.get(f"/api/v1{base}/summary.svg", params={"tool": "nos"})
        assert "★" in plot.text  # stars, not invented risk colours
