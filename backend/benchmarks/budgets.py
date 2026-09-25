"""The performance budgets of guide 2.2, measured on the running stack (Phase 9).

Makes a throwaway account (e2e-perf-…@example.com) and, as `make seed-large` does, a review
of 100,000 generated records. Then it times what a reviewer waits for, over HTTP through
the API's middleware, sessions and row-level security:

- the screening queue and saving a decision (budget: API p95 < 80 ms);
- the records list under every filter and sort (p95 < 150 ms at 100,000 records);
- importing 10,000 and 100,000 RIS records, from upload to done (< 10 s, < 60 s);
- deduplicating 50,000 records (< 30 s), timed by the worker's own job record.

Requests are paced under the API's per-user limit (600 a minute), as a person's are.
Everything it made is deleted at the end, whatever happens.

    make perf                      # or, in the api container:
    python -m benchmarks.budgets [--records 100000] [--json /tmp/budgets.json]
"""

import argparse
import asyncio
import csv
import json
import os
import random
import secrets
import statistics
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from arq.connections import ArqRedis, RedisSettings, create_pool
from arq.jobs import Job, JobStatus
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.cli import seed_large
from app.config import get_settings
from app.db import create_engine, create_sessionmaker
from app.models import Project, User
from app.security.passwords import Passwords
from app.services.dedup import dedup_job_id
from benchmarks.ranking import DATA

# The running API, by its compose service name (`make perf` runs in a container of its own).
API = os.environ.get("BUDGETS_API", "http://api:8000/api/v1")
# 600 requests a minute per user (app.security.rate_limit.API_PER_USER): stay under it.
PACE_SECONDS = 0.11
SAMPLES = 40


@dataclass
class Result:
    name: str
    budget: str
    measured: str
    passed: bool
    detail: dict[str, Any] = field(default_factory=dict)


def percentile(values: list[float], share: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(share * (len(ordered) - 1))))
    return ordered[index]


def summary(times: list[float]) -> dict[str, float]:
    return {
        "p50_ms": round(statistics.median(times), 1),
        "p95_ms": round(percentile(times, 0.95), 1),
        "max_ms": round(max(times), 1),
        "samples": len(times),
    }


class Client:
    """The API as the SPA uses it: session cookie, CSRF token, same Origin.

    The session cookie is `__Host-`, so always Secure, and httpx's cookie jar will not send
    it over this internal plain-HTTP hop; the cookies are carried by hand.
    """

    def __init__(self, origin: str) -> None:
        self.http = httpx.AsyncClient(base_url=API, headers={"Origin": origin}, timeout=300)
        self.cookies: dict[str, str] = {}
        self.overhead: list[float] = []

    def _keep(self, response: httpx.Response) -> httpx.Response:
        self.cookies.update(dict(response.cookies))
        if self.cookies:
            self.http.headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        return response

    async def refresh_csrf(self) -> None:
        token = self._keep(await self.http.get("/auth/csrf")).json()["csrf_token"]
        self.http.headers["X-CSRF-Token"] = token

    async def call(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = self._keep(await self.http.request(method, path, **kwargs))
        if response.status_code >= 400:
            raise RuntimeError(f"{method} {path} answered {response.status_code}: {response.text}")
        return response

    async def timed(self, method: str, path: str, **kwargs: Any) -> tuple[float, httpx.Response]:
        """The API's own time for a request (its Server-Timing header): the budgets are
        for the API, not for this machine's scheduler. What the client saw on top is
        kept in `overhead`."""
        await asyncio.sleep(PACE_SECONDS)
        started = time.perf_counter()
        response = await self.call(method, path, **kwargs)
        seen = (time.perf_counter() - started) * 1000
        timing = response.headers.get("server-timing", "")
        took = float(timing.split("dur=")[1]) if "dur=" in timing else seen
        self.overhead.append(seen - took)
        return took, response

    async def aclose(self) -> None:
        await self.http.aclose()


# Titles as varied as a real search's: an opener, a subject, a group, a design and a
# place, so that blocking, search and ranking meet the spread of words they would.
OPENERS = (
    "Effect of",
    "Association between",
    "Impact of",
    "Prevalence of",
    "Predictors of",
    "Outcomes of",
    "Determinants of",
    "Changes in",
    "Trends in",
    "Burden of",
    "A randomised trial of",
    "A cohort study of",
    "A qualitative study of",
    "Cost-effectiveness of",
    "Validation of",
    "Development of",
    "Barriers to",
    "Interventions for",
    "Screening for",
    "Management of",
)
SUBJECTS = (
    "sleep quality",
    "fatigue",
    "melatonin use",
    "circadian misalignment",
    "napping",
    "caffeine intake",
    "light exposure",
    "shift length",
    "rest breaks",
    "burnout",
    "medication errors",
    "needlestick injuries",
    "workplace violence",
    "job satisfaction",
    "turnover intention",
    "depressive symptoms",
    "anxiety",
    "cardiovascular risk",
    "metabolic syndrome",
    "body mass index",
    "blood pressure",
    "gastrointestinal symptoms",
    "cognitive performance",
    "reaction time",
    "driving after night shifts",
    "family life",
    "social jet lag",
    "sickness absence",
    "presenteeism",
    "resilience",
)
GROUPS = (
    "hospital nurses",
    "intensive care nurses",
    "paramedics",
    "junior doctors",
    "midwives",
    "police officers",
    "firefighters",
    "factory workers",
    "pilots",
    "air traffic controllers",
    "security guards",
    "care home staff",
    "pharmacists",
    "radiographers",
    "emergency physicians",
    "surgical residents",
    "truck drivers",
    "call centre workers",
    "miners",
    "seafarers",
)
DESIGNS = (
    "a cross-sectional survey",
    "a prospective cohort",
    "a randomised controlled trial",
    "a mixed-methods study",
    "a secondary analysis",
    "a multicentre study",
    "a pilot study",
    "a longitudinal analysis",
    "a case-control study",
    "a registry study",
)
PLACES = (
    "Norway",
    "Japan",
    "Brazil",
    "Nigeria",
    "Canada",
    "Bangladesh",
    "Germany",
    "Australia",
    "India",
    "South Korea",
    "the Netherlands",
    "Iran",
    "Chile",
    "Kenya",
    "the United Kingdom",
    "the United States",
    "Sweden",
    "Turkey",
    "China",
    "Ghana",
)
SURNAMES = (
    "Okafor",
    "Lindqvist",
    "Tanaka",
    "Silva",
    "Müller",
    "Rahman",
    "Chowdhury",
    "Smith",
    "Nakamura",
    "Haddad",
    "Kowalski",
    "Mensah",
    "Ivanova",
    "García",
    "Kim",
    "Nguyen",
    "Johansson",
    "Osei",
    "Rossi",
    "Dubois",
    "Singh",
    "Park",
    "Novak",
    "Ahmed",
    "Costa",
)
JOURNALS = (
    "Journal of Advanced Nursing",
    "Sleep Health",
    "Occupational and Environmental Medicine",
    "BMJ Open",
    "International Journal of Nursing Studies",
    "Chronobiology International",
    "Scandinavian Journal of Work, Environment and Health",
    "Sleep Medicine",
)


def real_records() -> list[dict[str, str]]:
    """Real titles, abstracts and keywords (SYNERGY, CC0) when `benchmarks/synergy.py` has
    fetched them: their spread of words is what blocking and search really meet."""
    rows: list[dict[str, str]] = []
    for path in sorted(DATA.glob("*.csv")):
        with path.open(encoding="utf-8") as source:
            rows += [row for row in csv.DictReader(source) if row["title"].strip()]
    return rows


def ris(count: int, *, tag: str, duplicates: float = 0.0) -> bytes:
    """`count` RIS records; a share of them again as another database writes them (the
    title in capitals, an abbreviated journal, the same DOI) for deduplication to find."""
    pick = random.Random(tag)
    real = real_records()
    originals = [record(pick, index, tag, real) for index in range(count - int(count * duplicates))]
    lines: list[str] = []
    for fields in originals:
        lines += as_ris(fields)
    for fields in pick.sample(originals, int(count * duplicates)):
        lines += as_ris({**fields, "TI": fields["TI"].upper(), "JO": "J Adv Nurs"})
    return "\n".join(lines).encode()


def record(pick: random.Random, index: int, tag: str, real: list[dict[str, str]]) -> dict[str, str]:
    subject, group = pick.choice(SUBJECTS), pick.choice(GROUPS)
    if real:
        row = real[index % len(real)]
        title, abstract, year = row["title"], row["abstract"], row["year"] or "2020"
    else:
        title = (
            f"{pick.choice(OPENERS)} {subject} in {group}: "
            f"{pick.choice(DESIGNS)} in {pick.choice(PLACES)}"
        )
        abstract = (
            f"We studied {subject} among {pick.randint(40, 4000)} {group} "
            f"working rotating night shifts, and compared them with day workers."
        )
        year = str(pick.randint(1990, 2025))
    return {
        "TI": " ".join(title.split()),
        "AU": f"{pick.choice(SURNAMES)}, {pick.choice('ABCDEFGHJKLMNPRST')}.",
        "PY": year,
        "JO": pick.choice(JOURNALS),
        "DO": f"10.1000/{tag}.{index}",
        "AB": " ".join(abstract.split()),
    }


def as_ris(fields: dict[str, str]) -> list[str]:
    return ["TY  - JOUR", *(f"{tag}  - {value}" for tag, value in fields.items()), "ER  - "]


async def job_seconds(queue: ArqRedis, job_id: str) -> float | None:
    """How long the worker spent on a job, by its own record (not counting any wait)."""
    info = await Job(job_id, queue).result_info()
    if info is None:
        return None
    return (info.finish_time - info.start_time).total_seconds()


async def wait_for(check: Callable[[], Awaitable[bool]], within: float) -> None:
    """Ask the API (or the job store) every half second: there is nothing to wait on."""
    async with asyncio.timeout(within):
        while True:
            if await check():
                return
            await asyncio.sleep(0.5)


async def import_file(
    client: Client, queue: ArqRedis, pid: str, name: str, body: bytes
) -> dict[str, float]:
    """Upload, confirm and wait: the whole wait a person sees, and the worker's part."""
    await client.refresh_csrf()
    started = time.perf_counter()
    uploaded = await client.call(
        "POST",
        f"/projects/{pid}/imports",
        files={"files": (name, body, "application/x-research-info-systems")},
        data={"database_name": "PubMed"},
    )
    batch = uploaded.json()["batches"][0]["id"]
    upload_done = time.perf_counter()
    accepted = await client.call(
        "POST", f"/projects/{pid}/imports/{batch}/confirm", json={"database_name": "PubMed"}
    )

    async def done() -> bool:
        history = (await client.call("GET", f"/projects/{pid}/imports")).json()
        status = next(item["status"] for item in history if item["id"] == batch)
        if status == "failed":
            raise RuntimeError(f"the import of {name} failed")
        return bool(status == "done")

    await wait_for(done, within=600)
    finished = time.perf_counter()
    worker = await job_seconds(queue, accepted.json()["job_id"])
    return {
        "total_s": round(finished - started, 1),
        "upload_s": round(upload_done - started, 1),
        "worker_s": round(worker, 1) if worker is not None else -1,
    }


async def new_review(client: Client, title: str) -> str:
    await client.refresh_csrf()
    created = await client.call("POST", "/projects", json={"title": title})
    return str(created.json()["id"])


async def screening(client: Client, pid: str) -> list[Result]:
    await client.refresh_csrf()
    await client.call(
        "PATCH", f"/projects/{pid}", json={"settings": {"reviewers_per_record_ta": 1}}
    )
    results: list[Result] = []
    for sort in ("relevance", "random"):
        queue_ms: list[float] = []
        decide_ms: list[float] = []
        for step in range(SAMPLES + 3):
            took, response = await client.timed(
                "GET", f"/projects/{pid}/screening/queue?stage=title_abstract&n=10&sort={sort}"
            )
            record = response.json()["items"][0]["id"]
            spent, _ = await client.timed(
                "PUT",
                f"/projects/{pid}/records/{record}/decision",
                json={
                    "stage": "title_abstract",
                    "decision": "include" if step % 4 == 0 else "exclude",
                },
            )
            if step >= 3:  # the first few warm the caches, as a session's first minute does
                queue_ms.append(took)
                decide_ms.append(spent)
        for name, times in (("next ten records", queue_ms), ("saving a decision", decide_ms)):
            stats = summary(times)
            results.append(
                Result(
                    f"Screening: {name} ({sort} order)",
                    "API p95 < 80 ms",
                    f"p95 {stats['p95_ms']} ms (p50 {stats['p50_ms']})",
                    stats["p95_ms"] < 80,
                    stats,
                )
            )
    return results


NEXT = "next page"
LIST_FILTERS: dict[str, dict[str, str]] = {
    "no filter, newest first": {},
    "pending": {"status": "pending"},
    "included": {"status": "included"},
    "excluded": {"status": "excluded"},
    "conflicts": {"status": "conflict"},
    "search: one word": {"q": "melatonin"},
    "search: phrase": {"q": '"night shifts"'},
    "search: author and years": {"q": "author:okafor year:2010..2024"},
    "search: a word left out": {"q": "sleep -melatonin"},
    "search: a DOI": {"q": "10.1000/winnow.54321"},
    "sorted by title": {"sort": "title"},
    "sorted by year": {"sort": "year"},
    "sorted by relevance": {"sort": "relevance"},
    "possible duplicates": {"duplicates": "true"},
    "second page": {"cursor": NEXT},
}


async def record_list(client: Client, pid: str) -> list[Result]:
    first = (await client.call("GET", f"/projects/{pid}/records?limit=50")).json()
    results: list[Result] = []
    for name, filters in LIST_FILTERS.items():
        params = {"limit": "50"} | {
            key: first["next_cursor"] if value == NEXT else value for key, value in filters.items()
        }
        times: list[float] = []
        for step in range(SAMPLES // 2 + 2):
            took, _ = await client.timed("GET", f"/projects/{pid}/records", params=params)
            if step >= 2:
                times.append(took)
        stats = summary(times)
        results.append(
            Result(
                f"Records list: {name}",
                "API p95 < 150 ms",
                f"p95 {stats['p95_ms']} ms (p50 {stats['p50_ms']})",
                stats["p95_ms"] < 150,
                stats,
            )
        )
    facets: list[float] = []
    for _ in range(SAMPLES // 2):
        took, _ = await client.timed("GET", f"/projects/{pid}/records/facets")
        facets.append(took)
    stats = summary(facets)
    results.append(
        Result(
            "Records list: the filter counts beside it",
            "API p95 < 150 ms",
            f"p95 {stats['p95_ms']} ms (p50 {stats['p50_ms']})",
            stats["p95_ms"] < 150,
            stats,
        )
    )
    return results


async def deduplicated(queue: ArqRedis, pid: str) -> float:
    """Wait for the dedup pass every import sets off, and say how long it ran.

    Dedup jobs keep no result (their id is freed for the next run the moment one ends),
    so this watches the job's status instead: waiting, running, then gone.
    """
    job = Job(dedup_job_id(uuid.UUID(pid)), queue)
    seen = False
    started: float | None = None
    async with asyncio.timeout(900):
        while True:
            status = await job.status()
            if status in (JobStatus.deferred, JobStatus.queued):
                seen = True
            elif status is JobStatus.in_progress:
                seen = True
                started = started or time.perf_counter()
            elif seen:  # gone: finished
                return time.perf_counter() - started if started else 0.0
            await asyncio.sleep(0.2)


async def imports_and_dedup(client: Client, queue: ArqRedis) -> list[Result]:
    """Each import on its own, after the last one's dedup pass has finished, so no two
    measurements share the worker."""
    results: list[Result] = []
    for count, budget in ((10_000, 10), (100_000, 60)):
        pid = await new_review(client, f"Import {count:,}")
        timing = await import_file(
            client, queue, pid, f"search-{count}.ris", ris(count, tag=f"i{count}")
        )
        results.append(
            Result(
                f"Import {count:,} RIS records",
                f"< {budget} s",
                f"{timing['total_s']} s "
                f"(upload {timing['upload_s']} s, worker {timing['worker_s']} s)",
                timing["total_s"] < budget,
                timing,
            )
        )
        await deduplicated(queue, pid)

    # 50,000 records, a tenth of them a second copy of another: the dedup pass that
    # follows the import on its own, timed by its job (its few seconds' settling not
    # counted).
    pid = await new_review(client, "Dedup 50,000")
    await import_file(client, queue, pid, "dedup-50000.ris", ris(50_000, tag="d", duplicates=0.1))
    seconds = await deduplicated(queue, pid)
    found = (await client.call("GET", f"/projects/{pid}/dedup/summary")).json()
    results.append(
        Result(
            "Deduplication, 50,000 records",
            "< 30 s",
            f"{seconds:.1f} s ({found['duplicates']:,} duplicates found)",
            0 <= seconds < 30,
            {"seconds": round(seconds, 1), **found},
        )
    )
    return results


async def section(name: str, measure: Callable[[], Awaitable[list[Result]]]) -> list[Result]:
    """One part of the run; if it breaks, say so and carry on with the rest."""
    try:
        return await measure()
    except Exception as error:  # a broken part is a result to report, not the end
        return [Result(name, "-", f"did not finish: {error!r}"[:200], False)]


async def settle(engine: AsyncEngine, statement: str = "VACUUM (ANALYZE) records") -> None:
    """Bring `records` to the state autovacuum keeps it in: dead rows from earlier runs
    cleared, statistics current after a bulk load. The budgets are for a settled
    database, not one halfway through maintenance. (A fixed statement, no input in it.)"""
    async with engine.connect() as connection:
        autocommit = await connection.execution_options(isolation_level="AUTOCOMMIT")
        await autocommit.exec_driver_sql(statement)


async def main(records: int, parts: set[str], keep: bool = False) -> list[Result]:
    settings = get_settings()
    if settings.is_production:
        raise SystemExit(
            "The budgets run on development instances only: they make and delete data."
        )
    engine = create_engine(settings)
    sessions = create_sessionmaker(engine)
    queue = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    email = f"e2e-perf-{secrets.token_hex(4)}@example.com"
    password = secrets.token_urlsafe(24)  # made here, used once, never shown
    client = Client(settings.public_origin)

    async with sessions() as db:
        db.add(
            User(
                email=email,
                name="Performance test",
                password_hash=await Passwords(settings).hash(password),
                email_verified_at=datetime.now(UTC),
            )
        )
        await db.commit()

    results: list[Result] = []
    try:
        await client.refresh_csrf()
        await client.call("POST", "/auth/login", json={"email": email, "password": password})
        # Imports first, on a quiet worker; then `make seed-large`'s review for the list
        # (before any decision sets a retrain off) and for screening.
        await settle(engine)
        if "imports" in parts:
            results += await section("Imports", lambda: imports_and_dedup(client, queue))
        if not parts & {"list", "screening"}:
            return results
        await seed_large(email, records)
        await settle(engine, "ANALYZE records")
        async with sessions() as db:
            owner = await db.scalar(select(User.id).where(User.email == email))
            pid = str(
                await db.scalar(
                    select(Project.id).where(
                        Project.owner_id == owner, Project.title.startswith("Performance test")
                    )
                )
            )
        if "list" in parts:
            results += await section("Records list", lambda: record_list(client, pid))
        if "screening" in parts:
            results += await section("Screening", lambda: screening(client, pid))
        if client.overhead:
            extra = summary(client.overhead)
            results.append(
                Result(
                    "(context) what the client saw on top of the API",
                    "-",
                    f"p50 {extra['p50_ms']} ms, p95 {extra['p95_ms']} ms; load average "
                    + ", ".join(f"{load:.1f}" for load in os.getloadavg()),
                    True,
                    extra,
                )
            )
    finally:
        await client.aclose()
        if keep:
            print(f"\nKept {email}'s reviews for a closer look; delete them when done.")
        else:
            async with sessions() as db:
                owner = await db.scalar(select(User.id).where(User.email == email))
                await db.execute(delete(Project).where(Project.owner_id == owner))
                await db.commit()
            # Leave the table as it was found, not full of dead rows for the next person.
            await settle(engine)
        await queue.aclose()
        await engine.dispose()

    return results


def report(results: list[Result], out: str | None) -> int:
    width = max(len(r.name) for r in results)
    print(f"\n{'Budget':<{width}}  {'Target':<16}  Measured")
    for r in results:
        mark = "ok  " if r.passed else "OVER"
        print(f"{r.name:<{width}}  {r.budget:<16}  {mark} {r.measured}")
    if out:
        Path(out).write_text(json.dumps([asdict(r) for r in results], indent=2), encoding="utf-8")
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--records", type=int, default=100_000)
    parser.add_argument("--json", dest="out")
    parser.add_argument(
        "--parts",
        default="imports,list,screening",
        help="which to measure, comma-separated: imports, list, screening",
    )
    parser.add_argument("--keep", action="store_true", help="leave the data for EXPLAIN")
    args = parser.parse_args()
    parts = set(args.parts.split(","))
    raise SystemExit(report(asyncio.run(main(args.records, parts, args.keep)), args.out))
