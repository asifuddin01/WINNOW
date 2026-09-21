"""RFC 9457 problem details, the body of every error response."""

from typing import Any

from pydantic import BaseModel, ConfigDict


class Problem(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    request_id: str | None = None


class ValidationIssue(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class ValidationProblem(Problem):
    errors: list[ValidationIssue]


PROBLEM_MEDIA_TYPE = "application/problem+json"


def problem_content(model: type[Problem] = Problem) -> dict[str, Any]:
    """OpenAPI `responses` entry for an error; documented as problem+json by the app."""
    return {"model": model}
