"""OpenAPI `responses` for errors shared by many routes, so the generated types know them."""

from typing import Any

from fastapi import status

from app.schemas.problem import problem_content

Responses = dict[int | str, dict[str, Any]]

UNAUTHORIZED: Responses = {status.HTTP_401_UNAUTHORIZED: problem_content()}
RATE_LIMITED: Responses = {status.HTTP_429_TOO_MANY_REQUESTS: problem_content()}
# Every /projects/{pid} route: signed out, not allowed, or not a member (or no such project).
PROJECT: Responses = {
    **UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN: problem_content(),
    status.HTTP_404_NOT_FOUND: problem_content(),
}
CONFLICT: Responses = {status.HTTP_409_CONFLICT: problem_content()}
