import hashlib

import httpx

from app.security.breach import is_breached

PASSWORD = "correct horse battery staple"
DIGEST = hashlib.sha1(PASSWORD.encode(), usedforsecurity=False).hexdigest().upper()


def client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


async def test_only_the_hash_prefix_leaves_the_server() -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=f"{DIGEST[5:]}:42\r\nFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF:0")

    async with client(httpx.MockTransport(respond)) as http:
        assert await is_breached(PASSWORD, http)
    assert seen[0].url.path == f"/range/{DIGEST[:5]}"
    assert seen[0].headers["Add-Padding"] == "true"
    assert DIGEST[5:] not in str(seen[0].url)
    assert PASSWORD not in str(seen[0].url)


async def test_padding_entries_do_not_count() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=f"{DIGEST[5:]}:0\r\nABC:3")

    async with client(httpx.MockTransport(respond)) as http:
        assert not await is_breached(PASSWORD, http)


async def test_an_unreachable_service_fails_open() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    async with client(httpx.MockTransport(respond)) as http:
        assert not await is_breached(PASSWORD, http)
    async with client(httpx.MockTransport(lambda r: httpx.Response(503))) as http:
        assert not await is_breached(PASSWORD, http)
