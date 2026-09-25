"""Every error leaves the API as application/problem+json (RFC 9457)."""

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, cast

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic.json_schema import models_json_schema
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.middleware import REQUEST_ID_HEADER
from app.schemas.problem import PROBLEM_MEDIA_TYPE, Problem, ValidationIssue, ValidationProblem
from app.services.errors import DomainError

log = structlog.get_logger(__name__)


class ProblemError(Exception):
    """Raise from a route or dependency to return a specific problem response."""

    def __init__(
        self,
        status: int,
        detail: str | None = None,
        *,
        code: str | None = None,
        headers: Mapping[str, str] | None = None,
        **extensions: Any,
    ) -> None:
        super().__init__(detail or HTTPStatus(status).phrase)
        self.status = status
        self.detail = detail
        self.code = code
        self.headers = headers
        self.extensions = extensions


def _request_id(request: Request) -> str | None:
    request_id: str | None = getattr(request.state, "request_id", None)
    return request_id


def problem_response(
    request: Request,
    problem: Problem,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    problem.request_id = _request_id(request)
    return JSONResponse(
        problem.model_dump(mode="json", exclude_none=True),
        status_code=problem.status,
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


async def _http_exception(request: Request, error: Exception) -> JSONResponse:
    exc = cast("StarletteHTTPException", error)
    title = HTTPStatus(exc.status_code).phrase
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail != title else None
    problem = Problem(title=title, status=exc.status_code, detail=detail)
    return problem_response(request, problem, headers=exc.headers)


async def _validation_error(request: Request, error: Exception) -> JSONResponse:
    exc = cast("RequestValidationError", error)
    # Report where and why, never the submitted value: it may be a password.
    issues = [
        ValidationIssue(loc=list(error["loc"]), msg=error["msg"], type=error["type"])
        for error in exc.errors()
    ]
    problem = ValidationProblem(
        title=HTTPStatus.UNPROCESSABLE_ENTITY.phrase,
        status=HTTPStatus.UNPROCESSABLE_ENTITY,
        detail="The request did not pass validation.",
        errors=issues,
    )
    return problem_response(request, problem)


async def _problem_error(request: Request, error: Exception) -> JSONResponse:
    exc = cast("ProblemError", error)
    problem = Problem(
        title=HTTPStatus(exc.status).phrase,
        status=exc.status,
        detail=exc.detail,
        code=exc.code,
        **exc.extensions,
    )
    return problem_response(request, problem, headers=exc.headers)


async def _domain_error(request: Request, error: Exception) -> JSONResponse:
    exc = cast("DomainError", error)
    problem = Problem(
        title=HTTPStatus(exc.status).phrase,
        status=exc.status,
        detail=exc.detail,
        code=exc.code,
        **exc.extensions,
    )
    return problem_response(request, problem)


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    # Runs in Starlette's outermost middleware, outside RequestContextMiddleware,
    # so set the request id header here as well.
    log.error("http.unhandled_exception", error=type(exc).__name__)
    problem = Problem(
        title=HTTPStatus.INTERNAL_SERVER_ERROR.phrase,
        status=HTTPStatus.INTERNAL_SERVER_ERROR,
        detail="Something went wrong on our side. Quote the request id if you report it.",
    )
    headers = {"Cache-Control": "no-store"}
    if request_id := _request_id(request):
        headers[REQUEST_ID_HEADER] = request_id
    return problem_response(request, problem, headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(ProblemError, _problem_error)
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(Exception, _unhandled)


def document_problem_responses(schema: dict[str, Any]) -> dict[str, Any]:
    """Make the OpenAPI document match the wire format.

    FastAPI documents every response body as application/json and 422s as its own
    HTTPValidationError. Ours are application/problem+json, with ValidationProblem for 422,
    and the generated frontend types depend on the document saying so.
    """
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    components.pop("HTTPValidationError", None)
    components.pop("ValidationError", None)
    _, definitions = models_json_schema(
        [(ValidationProblem, "validation")], ref_template="#/components/schemas/{model}"
    )
    components.update(definitions.get("$defs", {}))

    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            for code, response in operation.get("responses", {}).items():
                if not (code.isdigit() and int(code) >= HTTPStatus.BAD_REQUEST):
                    continue
                content = response.setdefault("content", {})
                body = content.pop("application/json", None)
                if code == str(HTTPStatus.UNPROCESSABLE_ENTITY.value):
                    body = {"schema": {"$ref": "#/components/schemas/ValidationProblem"}}
                content[PROBLEM_MEDIA_TYPE] = body or content.get(PROBLEM_MEDIA_TYPE) or {}
    return schema
