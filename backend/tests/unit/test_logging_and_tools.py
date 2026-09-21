import json
import logging
from collections.abc import Iterator

import pytest
import structlog

from app import openapi
from app.logging_config import configure_logging
from app.workers import settings as worker
from tests.conftest import make_settings


@pytest.fixture
def restore_logging() -> Iterator[None]:
    yield
    configure_logging(make_settings())


@pytest.mark.usefixtures("restore_logging")
def test_production_logs_are_json(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(make_settings(winnow_env="production", public_url="https://w.example.org"))
    structlog.get_logger("winnow.test").info("something.happened", records=3)
    logging.getLogger("uvicorn.error").warning("from uvicorn")
    lines = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    assert lines[0]["event"] == "something.happened"
    assert lines[0]["records"] == 3
    assert lines[0]["level"] == "info"
    assert lines[1]["event"] == "from uvicorn"
    assert logging.getLogger("uvicorn.access").disabled


def test_openapi_command_prints_the_schema(capsys: pytest.CaptureFixture[str]) -> None:
    openapi.main()
    schema = json.loads(capsys.readouterr().out)
    assert schema["info"]["title"] == "Winnow API"
    assert {"/api/v1/healthz", "/api/v1/readyz"} <= schema["paths"].keys()
    assert schema["paths"]["/api/v1/healthz"]["get"]["operationId"] == "healthz"


async def test_worker_ping_job() -> None:
    assert await worker.ping({}) == "pong"


async def test_worker_lifecycle_hooks_run() -> None:
    await worker.startup({})
    await worker.shutdown({})


def test_worker_settings_register_jobs() -> None:
    assert worker.ping in worker.WorkerSettings.functions
    assert worker.WorkerSettings.health_check_interval == 30
