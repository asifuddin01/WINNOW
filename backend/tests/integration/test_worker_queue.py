"""A job goes through Redis and comes back: the API side enqueues, a worker runs it."""

from arq import create_pool
from arq.connections import RedisSettings
from arq.worker import Worker

from app.config import Settings
from app.workers.settings import WorkerSettings


async def test_ping_job_round_trip(db_settings: Settings) -> None:
    redis_settings = RedisSettings.from_dsn(db_settings.redis_url)
    pool = await create_pool(redis_settings, default_queue_name="winnow:test")
    try:
        job = await pool.enqueue_job("ping")
        assert job is not None
        worker = Worker(
            functions=WorkerSettings.functions,
            redis_settings=redis_settings,
            queue_name="winnow:test",
            burst=True,
            poll_delay=0.05,
            handle_signals=False,
        )
        try:
            await worker.main()
        finally:
            await worker.close()
        assert await job.result(timeout=5) == "pong"
    finally:
        await pool.aclose()
