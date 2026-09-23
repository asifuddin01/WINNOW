"""AI suggestions end to end (guide 8.11): off by default, the owner opts in, a suggestion
is advice kept for the asker, and the review can export them all."""

import csv
import io
import json
from typing import Any

from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.llm.providers import ProviderError
from app.models import AuditLog, Decision, LlmSuggestion
from tests.conftest import MemoryMailer
from tests.project_helpers import api, get, post
from tests.screening_helpers import decide, settings, team

ANSWER = {
    "decision": "include",
    "confidence": 0.75,
    "criteria": [{"criterion": 1, "verdict": "met"}, {"criterion": 2, "verdict": "unclear"}],
    "rationale": '=HYPERLINK("x") Nurses on nights; the design is not stated.',
}


class FakeProvider:
    name = "anthropic"
    model = "claude-opus-5"

    def __init__(self, answer: str | Exception) -> None:
        self.answer = answer
        self.asked: list[str] = []

    async def complete(self, system: str, user: str, schema: dict[str, Any]) -> str:
        self.asked.append(user)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def with_provider(db_app: FastAPI, db_settings: Settings, answer: str | Exception) -> FakeProvider:
    """An instance whose administrator has set a provider up."""
    provider = FakeProvider(answer)
    db_app.state.llm = provider
    configured = db_settings.model_copy(update={"llm_provider": "anthropic", "llm_api_key": "k"})
    db_app.state.settings = configured
    return provider


async def add_criteria(client: Any, pid: str) -> None:
    for kind, text in (("inclusion", "Adults on night shifts"), ("exclusion", "Case reports")):
        response = await post(client, f"/projects/{pid}/criteria", {"kind": kind, "text": text})
        assert response.status_code == 201, response.text


async def test_suggestions_are_off_until_the_instance_and_the_owner_turn_them_on(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, db_settings: Settings
) -> None:
    async with team(db_app, db, mailer) as t:
        record = t.records[0]
        path = f"/projects/{t.pid}/records/{record}/llm-suggest"
        # No provider on this instance: nothing to turn on, nothing to ask.
        assert (await post(t.reviewer, path)).json()["code"] == "feature_unavailable"
        refused = await api(
            t.owner, "PATCH", f"/projects/{t.pid}", {"settings": {"llm_assist_enabled": True}}
        )
        assert refused.status_code == 409

        with_provider(db_app, db_settings, json.dumps(ANSWER))
        options = (await t.owner.get("/api/v1/auth/options")).json()
        assert options["llm_available"] is True
        # The provider exists, but this review has not opted in.
        assert (await post(t.reviewer, path)).json()["code"] == "feature_unavailable"
        # Only the owner opts in; anyone who edits the settings may opt out again.
        from tests.project_helpers import add_member, person

        async with person(db_app, mailer, "al@example.org", ip="10.9.0.8") as admin:
            await add_member(t.owner, admin, t.pid, "al@example.org", role="admin")
            by_admin = await api(
                admin, "PATCH", f"/projects/{t.pid}", {"settings": {"llm_assist_enabled": True}}
            )
            assert by_admin.status_code == 403
            await settings(t.owner, t.pid, llm_assist_enabled=True)
            await settings(admin, t.pid, llm_assist_enabled=False)


async def test_a_suggestion_is_advice_kept_for_the_asker_only(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, db_settings: Settings
) -> None:
    async with team(db_app, db, mailer) as t:
        provider = with_provider(db_app, db_settings, json.dumps(ANSWER))
        await add_criteria(t.owner, t.pid)
        await settings(t.owner, t.pid, llm_assist_enabled=True)
        record = t.records[0]
        path = f"/projects/{t.pid}/records/{record}/llm-suggest"

        assert (await get(t.reviewer, path)).json() == {"suggestion": None}
        asked = await post(t.reviewer, path)
        assert asked.status_code == 200, asked.text
        suggestion = asked.json()
        assert (suggestion["decision"], suggestion["confidence"]) == ("include", 0.75)
        assert [(c["text"], c["verdict"]) for c in suggestion["criteria"]] == [
            ("Adults on night shifts", "met"),
            ("Case reports", "unclear"),
        ]
        assert "Adults on night shifts" in provider.asked[0]
        # Advice only: no decision was made, and nothing about the answer is audited but
        # the fact that it was asked.
        assert await db.scalar(select(func.count()).select_from(Decision)) == 0
        logged = await db.scalar(select(AuditLog).where(AuditLog.action == "llm.suggested"))
        assert logged is not None
        assert logged.after == {
            "stage": "title_abstract",
            "provider": "anthropic",
            "model": "claude-opus-5",
        }

        # Seeing it again asks nobody; the other reviewer does not see it at all.
        assert (await get(t.reviewer, path)).json()["suggestion"]["id"] == suggestion["id"]
        assert (await get(t.owner, path)).json() == {"suggestion": None}
        assert len(provider.asked) == 1

        # The export, for the methods section: owners and admins only, formula-safe.
        await decide(t.reviewer, t.pid, record, "exclude")
        export = await get(t.owner, f"/projects/{t.pid}/llm-suggestions.csv")
        assert export.headers["content-type"].startswith("text/csv")
        rows = list(csv.DictReader(io.StringIO(export.text)))
        assert rows[0]["suggested"] == "include"
        assert rows[0]["reviewer_decision"] == "exclude"
        assert rows[0]["reviewer"] == (await get(t.reviewer, "/auth/me")).json()["name"]
        assert rows[0]["rationale"].startswith("'=HYPERLINK")
        assert rows[0]["criteria"] == "Adults on night shifts: met; Case reports: unclear"
        denied = await get(t.reviewer, f"/projects/{t.pid}/llm-suggestions.csv")
        assert denied.status_code == 403


async def test_a_provider_that_fails_says_so_and_keeps_nothing(
    db_app: FastAPI, db: AsyncSession, mailer: MemoryMailer, db_settings: Settings
) -> None:
    async with team(db_app, db, mailer) as t:
        with_provider(db_app, db_settings, ProviderError("The AI provider is busy."))
        await settings(t.owner, t.pid, llm_assist_enabled=True)
        path = f"/projects/{t.pid}/records/{t.records[0]}/llm-suggest"
        failed = await post(t.reviewer, path)
        assert failed.status_code == 502
        assert failed.json()["detail"] == "The AI provider is busy."

        db_app.state.llm = FakeProvider('{"decision": "include"}')
        unreadable = await post(t.reviewer, path)
        assert unreadable.status_code == 502
        assert unreadable.json()["code"] == "llm_failed"
        assert await db.scalar(select(func.count()).select_from(LlmSuggestion)) == 0

        missing = await post(t.reviewer, f"/projects/{t.pid}/records/{t.pid}/llm-suggest")
        assert missing.status_code == 404
