"""ARQ worker entry point: `arq app.workers.settings.WorkerSettings`.

Imports, deduplication, ranking, PDF processing and exports run here, never in a request.
"""

import asyncio
import uuid
from typing import Any, ClassVar

import structlog
from arq.connections import RedisSettings
from arq.typing import WorkerCoroutine
from arq.worker import Function, func

from app.config import get_settings
from app.db import create_engine, create_sessionmaker
from app.email.mailer import SEND_EMAIL_JOB, deliver
from app.email.messages import Email
from app.logging_config import configure_logging
from app.redis_client import create_redis
from app.storage import create_storage
from app.workers.imports import run_import

IMPORT_RECORDS_JOB = "import_records"

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
    )


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
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    health_check_interval = 30
