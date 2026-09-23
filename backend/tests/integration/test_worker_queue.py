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


async def test_a_burst_of_imports_queues_one_dedup_run(db_settings: Settings) -> None:
    """Twenty files finish as twenty imports within seconds; they must make one dedup run.

    Two runs at once on one review would each replace the other's pending clusters and
    could merge the same records twice.
    """
    import uuid

    from app.services.dedup import dedup_job_id, enqueue_dedup

    redis_settings = RedisSettings.from_dsn(db_settings.redis_url)
    pool = await create_pool(redis_settings, default_queue_name="winnow:test-dedup")
    project_id = uuid.uuid4()
    try:
        first = await enqueue_dedup(pool, project_id, settle=60)
        repeats = [await enqueue_dedup(pool, project_id, settle=60) for _ in range(19)]
        assert first == dedup_job_id(project_id)
        assert repeats == [None] * 19
        # Another review is not held up by this one.
        assert await enqueue_dedup(pool, uuid.uuid4(), settle=60) is not None
    finally:
        await pool.flushdb()
        await pool.aclose()
