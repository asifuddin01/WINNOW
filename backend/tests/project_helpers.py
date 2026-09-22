"""Helpers for driving the project API the way the app does."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient, Response

from tests.auth_helpers import csrf, signed_in
from tests.conftest import MemoryMailer, make_client

API = "/api/v1"
OWNER = "ada@example.org"
REVIEWER = "grace@example.org"


async def api(
    client: AsyncClient, method: str, path: str, body: dict[str, Any] | None = None
) -> Response:
    """A call with a fresh CSRF token, like the SPA makes."""
    return await client.request(
        method, f"{API}{path}", json=body, headers={"X-CSRF-Token": await csrf(client)}
    )


async def get(client: AsyncClient, path: str) -> Response:
    return await api(client, "GET", path)


async def post(client: AsyncClient, path: str, body: dict[str, Any] | None = None) -> Response:
    return await api(client, "POST", path, body)


async def patch(client: AsyncClient, path: str, body: dict[str, Any] | None = None) -> Response:
    return await api(client, "PATCH", path, body)


async def delete(client: AsyncClient, path: str) -> Response:
    return await api(client, "DELETE", path)


async def create_project(
    client: AsyncClient, title: str = "Sleep and shift work", **extra: Any
) -> dict[str, Any]:
    response = await post(client, "/projects", {"title": title, **extra})
    assert response.status_code == 201, response.text
    project: dict[str, Any] = response.json()
    return project


@asynccontextmanager
async def person(
    app: FastAPI, mailer: MemoryMailer, email: str, ip: str = "127.0.0.1"
) -> AsyncIterator[AsyncClient]:
    """A registered, confirmed, signed-in person with their own browser.

    Each gets their own IP: registration is rate limited per address (guide 12.6).
    """
    async with make_client(app, ip=ip) as client:
        await signed_in(client, mailer, email)
        yield client


async def invite(
    client: AsyncClient, project_id: str, email: str, role: str = "reviewer"
) -> dict[str, Any]:
    response = await post(client, f"/projects/{project_id}/invites", {"email": email, "role": role})
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def token_from(link: str) -> str:
    return link.rsplit("/", 1)[1]


async def add_member(
    owner_client: AsyncClient,
    joiner: AsyncClient,
    project_id: str,
    email: str,
    role: str = "reviewer",
) -> str:
    """Invite someone and have them accept, as the two of them would."""
    created = await invite(owner_client, project_id, email, role)
    response = await post(joiner, f"/invites/{token_from(created['link'])}/accept")
    assert response.status_code == 200, response.text
    accepted: str = response.json()["project_id"]
    return accepted
