"""Finding a free copy, and fetching it without being turned against the network
(guide 8.8, 12.4)."""

import json
from collections.abc import Callable

import httpx
import pytest

from app.fulltext import openaccess
from tests.pdf_helpers import tiny_pdf

Handler = Callable[[httpx.Request], httpx.Response]

PMC_LISTING = b"""<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <Contents><Key>PMC7012345.1/PMC7012345.1.pdf</Key></Contents>
  <Contents><Key>PMC7012345.1/PMC7012345.1.xml</Key></Contents>
  <Contents><Key>PMC7012345.2/PMC7012345.2.pdf</Key></Contents>
  <Contents><Key>PMC7012345.10/330_2026_12322_MOESM1_ESM.pdf</Key></Contents>
  <Contents><Key>PMC7012345.10/PMC7012345.10.pdf</Key></Contents>
</ListBucketResult>"""

UNPAYWALL = {
    "oa_locations": [
        {
            "url_for_pdf": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7012345/pdf/x.pdf",
            "version": "publishedVersion",
            "license": "cc-by",
        },
        {"url_for_pdf": "http://insecure.example.org/paper.pdf", "version": "acceptedVersion"},
        {"url_for_pdf": None, "url": "https://example.org/landing"},
        "garbage",
    ]
}


def client(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_pmc_then_unpaywall() -> None:
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        if request.url.host == "pmc-oa-opendata.s3.amazonaws.com":
            assert request.url.params["prefix"] == "PMC7012345."
            return httpx.Response(200, content=PMC_LISTING)
        assert request.url.params["email"] == "me@example.org"
        return httpx.Response(200, json=UNPAYWALL)

    async with client(handler) as http:
        found = await openaccess.find(
            http, doi="10.1000/x y", pmcid="PMC7012345", email="me@example.org"
        )
    assert [(c.source, c.url) for c in found] == [
        ("pmc", f"{openaccess.PMC_BUCKET}/PMC7012345.10/PMC7012345.10.pdf"),
        ("unpaywall", "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7012345/pdf/x.pdf"),
    ]
    assert found[1].license == "cc-by"
    assert found[0].host == "pmc-oa-opendata.s3.amazonaws.com"
    assert len({c.id for c in found}) == 2
    assert "10.1000/x%20y" in asked[1]


async def test_a_supplement_alone_is_not_the_article() -> None:
    """Seen on a real review: the only PDF besides the article was its ESM supplement."""
    listing = b"""<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
      <Contents><Key>PMC1.1/330_2026_1_MOESM1_ESM.pdf</Key></Contents>
      <Contents><Key>PMC1.1/PMC1.1.xml</Key></Contents>
    </ListBucketResult>"""
    async with client(lambda request: httpx.Response(200, content=listing)) as http:
        assert await openaccess.find(http, doi=None, pmcid="PMC1", email=None) == []


async def test_without_an_email_unpaywall_is_not_asked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("nothing should be asked")

    async with client(handler) as http:
        assert await openaccess.find(http, doi="10.1/x", pmcid=None, email=None) == []
        assert await openaccess.find(http, doi=None, pmcid="not-a-pmcid", email=None) == []


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(404),
        httpx.Response(200, content=b"not json"),
        httpx.Response(200, json={"oa_locations": "nope"}),
    ],
)
async def test_bad_answers_find_nothing(response: httpx.Response) -> None:
    async with client(lambda request: response) as http:
        assert await openaccess.find(http, doi="10.1/x", pmcid=None, email="a@b.org") == []


async def test_bad_pmc_answers_find_nothing() -> None:
    for answer in (httpx.Response(500), httpx.Response(200, content=b"<not xml")):

        def reply(request: httpx.Request, answer: httpx.Response = answer) -> httpx.Response:
            return answer

        async with client(reply) as http:
            assert await openaccess.find(http, doi=None, pmcid="PMC1", email=None) == []

    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    async with client(broken) as http:
        assert await openaccess.find(http, doi="10.1/x", pmcid="PMC1", email="a@b.org") == []


@pytest.fixture
def public(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every host counts as public, for tests of what happens after the address check."""

    async def anywhere(host: str, port: int) -> None:
        return None

    monkeypatch.setattr(openaccess, "_require_public", anywhere)


@pytest.mark.usefixtures("public")
async def test_download_follows_https_redirects_and_returns_the_pdf() -> None:
    pdf = tiny_pdf()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/paper.pdf"})
        return httpx.Response(200, content=pdf)

    async with client(handler) as http:
        assert await openaccess.download(http, "https://example.org/start", limit=10**6) == pdf


@pytest.mark.usefixtures("public")
async def test_download_refuses_what_it_should() -> None:
    def to_http(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})

    def loop(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/again"})

    def big(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF-" + bytes(2000))

    def missing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    cases = [
        (to_http, "Only https"),
        (loop, "too many times"),
        (big, "larger"),
        (missing, "answered 403"),
        (down, "could not be reached"),
    ]
    for handler, message in cases:
        async with client(handler) as http:
            with pytest.raises(openaccess.FetchError, match=message):
                await openaccess.download(http, "https://example.org/x", limit=1000)
    async with client(missing) as http:
        with pytest.raises(openaccess.FetchError, match="Only https"):
            await openaccess.download(http, "file:///etc/passwd", limit=1000)


LOCAL = ["127.0.0.1", "10.1.2.3", "169.254.169.254", "::1", "0.0.0.0"]  # noqa: S104


@pytest.mark.parametrize("host", LOCAL)
async def test_private_and_local_addresses_are_refused(host: str) -> None:
    with pytest.raises(openaccess.FetchError, match="public internet"):
        await openaccess._require_public(host, 443)


async def test_a_name_that_does_not_resolve() -> None:
    with pytest.raises(openaccess.FetchError, match="could not be found"):
        await openaccess._require_public("no-such-host.invalid", 443)


def test_the_address_really_connected_to_is_checked_too() -> None:
    class Stream:
        def __init__(self, address: str) -> None:
            self.address = address

        def get_extra_info(self, name: str) -> tuple[str, int]:
            assert name == "server_addr"
            return (self.address, 443)

    inside = httpx.Response(200, extensions={"network_stream": Stream("192.168.1.5")})
    with pytest.raises(openaccess.FetchError):
        openaccess._check_peer(inside)
    openaccess._check_peer(httpx.Response(200, extensions={"network_stream": Stream("1.1.1.1")}))
    openaccess._check_peer(httpx.Response(200))


def test_unpaywall_json_shape_is_what_we_read() -> None:
    assert json.loads(json.dumps(UNPAYWALL))["oa_locations"][0]["version"] == "publishedVersion"
