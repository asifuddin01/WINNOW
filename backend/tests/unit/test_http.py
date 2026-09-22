"""App factory behaviour that needs no database: errors, request ids, headers, docs."""

import logging
import re

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.errors import ProblemError
from app.main import create_app
from tests.conftest import PRODUCTION_ARGON2, make_settings

PROBLEM = "application/problem+json"


@pytest.fixture
def app(app: FastAPI) -> FastAPI:
    """The real app plus a few throwaway routes that exercise the error paths."""

    @app.get("/api/v1/_test/number")
    async def number(value: int) -> dict[str, int]:
        return {"value": value}

    @app.get("/api/v1/_test/items/{token}")
    async def item(token: str) -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/api/v1/_test/problem")
    async def problem() -> None:
        raise ProblemError(409, "Already there.", hint="try another")

    @app.get("/api/v1/_test/crash")
    async def crash() -> None:
        raise RuntimeError("secret internals")

    return app


async def test_healthz_is_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_unknown_route_is_a_problem_response(client: AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM
    body = response.json()
    assert body["title"] == "Not Found"
    assert body["status"] == 404
    assert body["request_id"] == response.headers["x-request-id"]


async def test_wrong_method_is_a_problem_response(client: AsyncClient) -> None:
    response = await client.delete("/api/v1/healthz")
    assert response.status_code == 405
    assert response.headers["content-type"] == PROBLEM
    assert "GET" in response.headers["allow"]


async def test_validation_errors_never_echo_the_submitted_value(client: AsyncClient) -> None:
    response = await client.get("/api/v1/_test/number", params={"value": "hunter2-password"})
    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM
    body = response.json()
    assert body["errors"][0]["loc"] == ["query", "value"]
    assert "hunter2" not in response.text


async def test_problem_error_carries_extensions(client: AsyncClient) -> None:
    response = await client.get("/api/v1/_test/problem")
    assert response.status_code == 409
    body = response.json()
    assert body["title"] == "Conflict"
    assert body["detail"] == "Already there."
    assert body["hint"] == "try another"


async def test_unhandled_error_is_generic_and_traceable(client: AsyncClient) -> None:
    response = await client.get("/api/v1/_test/crash")
    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM
    assert "secret internals" not in response.text
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert response.headers["cache-control"] == "no-store"


async def test_request_id_is_generated(client: AsyncClient) -> None:
    response = await client.get("/api/v1/healthz")
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-request-id"])


async def test_plain_request_id_is_propagated(client: AsyncClient) -> None:
    response = await client.get("/api/v1/healthz", headers={"X-Request-ID": "trace-abc.123"})
    assert response.headers["x-request-id"] == "trace-abc.123"


@pytest.mark.parametrize("hostile", ["a" * 129, "x y", 'evil" status=200'])
async def test_hostile_request_id_is_replaced(client: AsyncClient, hostile: str) -> None:
    response = await client.get("/api/v1/healthz", headers={"X-Request-ID": hostile})
    assert response.headers["x-request-id"] != hostile
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-request-id"])


async def test_api_responses_are_not_cached(client: AsyncClient) -> None:
    response = await client.get("/api/v1/healthz")
    assert response.headers["cache-control"] == "no-store"


async def test_access_log_uses_route_template_not_raw_path(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="winnow.http")
    await client.get("/api/v1/_test/items/invite-token-s3cr3t")
    entries = [r.msg for r in caplog.records if isinstance(r.msg, dict)]
    request_logs = [e for e in entries if e.get("event") == "http.request"]
    assert request_logs[-1]["route"] == "/api/v1/_test/items/{token}"
    assert request_logs[-1]["status"] == 200
    assert "invite-token-s3cr3t" not in caplog.text


async def test_docs_are_served_in_development(client: AsyncClient) -> None:
    assert (await client.get("/api/docs")).status_code == 200
    schema = (await client.get("/api/openapi.json")).json()
    assert "/api/v1/healthz" in schema["paths"]


async def test_docs_are_hidden_in_production() -> None:
    settings = make_settings(
        winnow_env="production", **PRODUCTION_ARGON2, public_url="https://winnow.example.org"
    )
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        assert (await client.get("/api/docs")).status_code == 404
        assert (await client.get("/api/openapi.json")).status_code == 404


async def test_openapi_documents_errors_as_problem_json(app: FastAPI) -> None:
    schema = app.openapi()
    unavailable = schema["paths"]["/api/v1/readyz"]["get"]["responses"]["503"]["content"]
    assert unavailable == {PROBLEM: {"schema": {"$ref": "#/components/schemas/Problem"}}}
    invalid = schema["paths"]["/api/v1/_test/number"]["get"]["responses"]["422"]["content"]
    assert invalid == {PROBLEM: {"schema": {"$ref": "#/components/schemas/ValidationProblem"}}}
    components = schema["components"]["schemas"]
    assert {"Problem", "ValidationProblem", "ValidationIssue"} <= components.keys()
    assert "HTTPValidationError" not in components
