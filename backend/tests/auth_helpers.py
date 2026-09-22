"""Small helpers for driving /auth the way the SPA does."""

from typing import Any

import pyotp
from httpx import AsyncClient, Response

from tests.conftest import MemoryMailer

PASSWORD = "a sturdy passphrase for tests"
AUTH = "/api/v1/auth"


async def csrf(client: AsyncClient) -> str:
    response = await client.get(f"{AUTH}/csrf")
    assert response.status_code == 200
    token: str = response.json()["csrf_token"]
    return token


async def post(
    client: AsyncClient, path: str, body: dict[str, Any] | None = None, token: str | None = None
) -> Response:
    """A write with a fresh CSRF token unless one is given."""
    return await client.post(
        f"{AUTH}{path}", json=body, headers={"X-CSRF-Token": token or await csrf(client)}
    )


async def delete(client: AsyncClient, path: str) -> Response:
    return await client.delete(f"{AUTH}{path}", headers={"X-CSRF-Token": await csrf(client)})


async def register(
    client: AsyncClient, email: str, password: str = PASSWORD, name: str = "Ada Lovelace"
) -> Response:
    return await post(client, "/register", {"name": name, "email": email, "password": password})


async def register_verified(
    client: AsyncClient, mailer: MemoryMailer, email: str, password: str = PASSWORD
) -> None:
    assert (await register(client, email, password)).status_code == 202
    response = await post(client, "/verify-email", {"token": mailer.token(email, "verify")})
    assert response.status_code == 200, response.text


async def login(
    client: AsyncClient, email: str, password: str = PASSWORD, totp: str | None = None
) -> Response:
    body: dict[str, Any] = {"email": email, "password": password}
    if totp is not None:
        body["totp"] = totp
    return await post(client, "/login", body)


async def signed_in(
    client: AsyncClient, mailer: MemoryMailer, email: str = "ada@example.org"
) -> str:
    """Register, verify and sign in; returns the session's CSRF token."""
    await register_verified(client, mailer, email)
    response = await login(client, email)
    assert response.status_code == 200, response.text
    token: str = response.json()["csrf_token"]
    return token


async def enable_two_factor(client: AsyncClient) -> tuple[pyotp.TOTP, list[str]]:
    setup = await post(client, "/2fa/setup")
    assert setup.status_code == 200, setup.text
    otp = pyotp.TOTP(setup.json()["secret"])
    enabled = await post(client, "/2fa/enable", {"code": otp.now()})
    assert enabled.status_code == 200, enabled.text
    codes: list[str] = enabled.json()["recovery_codes"]
    return otp, codes


def session_id(response: Response) -> str:
    """The session id a response set, from its Set-Cookie header."""
    header = session_cookie(response)
    assert header is not None, "no session cookie was set"
    return header.split(";", 1)[0].split("=", 1)[1]


def session_cookie(response: Response) -> str | None:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith("__Host-winnow_session="):
            return header
    return None
