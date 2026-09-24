"""ARQ worker entry point: `arq app.workers.settings.WorkerSettings`.

Imports, deduplication, ranking, PDF processing and exports run here, never in a request.
"""

import asyncio
import uuid
from typing import Any, ClassVar

import structlog
from arq.connections import RedisSettings
from arq.cron import CronJob, cron
from arq.typing import WorkerCoroutine
from arq.worker import Function, func

from app.config import get_settings
from app.db import create_engine, create_sessionmaker
from app.email.mailer import SEND_EMAIL_JOB, deliver
from app.email.messages import Email
from app.logging_config import configure_logging
from app.models import ScreeningStage
from app.redis_client import create_redis
from app.services.fulltext import BATCH_JOB, SCAN_JOB
from app.storage import create_storage
from app.workers.dedup import run_dedup
from app.workers.fulltext import SCAN_TRIES, discard_stale_batches, run_batch, run_scan
from app.workers.imports import run_import
from app.workers.ranking import run_ranking

IMPORT_RECORDS_JOB = "import_records"
DEDUP_JOB = "dedup_project"
RANK_JOB = "rank_project"

log = structlog.get_logger(__name__)


async def ping(ctx: dict[str, Any]) -> str:
    """Round-trip check for the queue: enqueue `ping` and expect "pong"."""
    return "pong"


async def send_email(ctx: dict[str, Any], to: str, subject: str, body: str) -> None:
    """Deliver one email over SMTP, off the event loop."""
    await asyncio.to_thread(deliver, get_settings(), Email(to, subject, body))


async def import_records(ctx: dict[str, Any], batch_id: str) -> dict[str, int]:
    """Load one uploaded file into `records`, with live progress (guide 8.3)."""
    return await run_import(
        sessionmaker=ctx["sessionmaker"],
        redis=ctx["events"],
        storage=ctx["storage"],
        batch_id=uuid.UUID(batch_id),
        # arq hands the job its own client, which is how one job asks for the next.
        queue=ctx["redis"],
    )


async def dedup_project(ctx: dict[str, Any], project_id: str) -> dict[str, int]:
    """Find duplicate clusters in one review (guide 9.1)."""
    result = await run_dedup(
        sessionmaker=ctx["sessionmaker"],
        redis=ctx["events"],
        project_id=uuid.UUID(project_id),
    )
    return {
        "records": result.records,
        "clusters": result.clusters,
        "duplicates": result.duplicates,
        "auto_resolved": result.auto_resolved,
    }


async def rank_project(ctx: dict[str, Any], project_id: str, stage: str) -> dict[str, Any]:
    """Train on a stage's decisions and score what is left (guide 8.10, 9.2)."""
    result = await run_ranking(
        sessionmaker=ctx["sessionmaker"],
        redis=ctx["events"],
        project_id=uuid.UUID(project_id),
        stage=ScreeningStage(stage),
    )
    return {"trained": result.trained, "labeled": result.labeled, "scored": result.scored}


async def scan_fulltext(ctx: dict[str, Any], fulltext_id: str) -> str | None:
    """Scan one PDF, quarantine it if it is infected, read its text if not (guide 12.4)."""
    outcome = await run_scan(
        sessionmaker=ctx["sessionmaker"],
        redis=ctx["events"],
        queue=ctx["redis"],
        storage=ctx["storage"],
        settings=get_settings(),
        fulltext_id=uuid.UUID(fulltext_id),
        attempt=ctx["job_try"],
    )
    return None if outcome is None else outcome.status.value


async def match_fulltext_batch(ctx: dict[str, Any], batch_id: str) -> int:
    """Unpack a ZIP of PDFs and match each to a record (guide 8.8)."""
    return await run_batch(
        sessionmaker=ctx["sessionmaker"],
        redis=ctx["events"],
        storage=ctx["storage"],
        settings=get_settings(),
        batch_id=uuid.UUID(batch_id),
    )


async def tidy_fulltext_batches(ctx: dict[str, Any]) -> int:
    return await discard_stale_batches(sessionmaker=ctx["sessionmaker"], storage=ctx["storage"])


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings)
    engine = create_engine(settings)
    ctx["engine"] = engine
    ctx["sessionmaker"] = create_sessionmaker(engine)
    # arq's own client speaks bytes; events are text, so they get their own client.
    ctx["events"] = create_redis(settings)
    ctx["storage"] = create_storage(settings)
    log.info("worker.started")


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["events"].aclose()
    await ctx["engine"].dispose()
    log.info("worker.stopped")


class WorkerSettings:
    functions: ClassVar[list[WorkerCoroutine | Function]] = [
        ping,
        # Job arguments include one-time links: keep no result behind, retry a flaky server.
        func(send_email, name=SEND_EMAIL_JOB, keep_result=0, max_tries=5),
        # An import can take a minute for 100,000 records; one attempt, and the batch row
        # records what happened either way.
        func(import_records, name=IMPORT_RECORDS_JOB, max_tries=1, timeout=1800),
        # Deduplication reads the whole project; 50,000 records take well under a minute
        # (guide 2.2), but a very large review is given room.
        # keep_result=0 frees the per-review job id as soon as a run ends (see
        # app.services.dedup.enqueue_dedup), so the next import can queue the next run.
        func(dedup_project, name=DEDUP_JOB, max_tries=1, timeout=1800, keep_result=0),
        # One run per review and stage at a time (app.services.ranking.ranking_job_id);
        # keep_result=0 frees the id for the next run the moment this one ends.
        func(rank_project, name=RANK_JOB, max_tries=1, timeout=600, keep_result=0),
        # Retried while the scanner is starting or reloading its signatures; each try waits
        # longer. The file stays unavailable until a scan says it is clean.
        func(scan_fulltext, name=SCAN_JOB, max_tries=SCAN_TRIES, timeout=600, keep_result=0),
        func(match_fulltext_batch, name=BATCH_JOB, max_tries=1, timeout=1800, keep_result=0),
    ]
    cron_jobs: ClassVar[list[CronJob]] = [
        cron(tidy_fulltext_batches, minute={17}, run_at_startup=False, keep_result=0),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    health_check_interval = 30
