"""The daily email digest of unread notifications (guide 8.17), off by default."""

from datetime import UTC, datetime

import structlog
from arq.connections import ArqRedis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.email.mailer import SEND_EMAIL_JOB
from app.email.messages import daily_digest
from app.services.notifications import digest_line, digests_due

log = structlog.get_logger(__name__)


async def send_digests(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    queue: ArqRedis,
    settings: Settings,
    now: datetime | None = None,
) -> int:
    """Queue one email per person due one; returns how many were queued."""
    moment = now or datetime.now(UTC)
    sent = 0
    async with sessionmaker() as db:
        for person, news in await digests_due(db, moment):
            message = daily_digest(
                person.email,
                person.name,
                [digest_line(row) for row in news],
                link=settings.public_origin,
                settings_link=f"{settings.public_origin}/account",
            )
            await queue.enqueue_job(SEND_EMAIL_JOB, message.to, message.subject, message.body)
            person.preferences = {**person.preferences, "digest_sent_at": moment.isoformat()}
            sent += 1
        await db.commit()
    log.info("digest.sent", count=sent)
    return sent
