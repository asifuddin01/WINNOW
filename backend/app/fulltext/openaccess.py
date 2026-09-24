"""Finding and fetching a free, legal copy of a paper (guide 8.8's "Find free full text").

Two sources, both open: Unpaywall, by DOI (it asks for a contact email), and PubMed
Central's open-access collection, by PMCID, from its public bucket. The server fetches the
chosen PDF itself — so the download is guarded: https only, every host resolved and
required to be on the public internet (checked again after connecting, and on every
redirect), a size cap, and the PDF's magic bytes afterwards. The links come from those two
services, never from the browser; the browser only picks one of them by its id.
"""

import asyncio
import hashlib
import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote, urljoin, urlsplit

import httpx
from defusedxml import ElementTree

UNPAYWALL = "https://api.unpaywall.org/v2/{doi}"
PMC_BUCKET = "https://pmc-oa-opendata.s3.amazonaws.com"
TIMEOUT_SECONDS = 30.0
MAX_REDIRECTS = 5
S3 = "{http://s3.amazonaws.com/doc/2006-03-01/}"

Source = Literal["unpaywall", "pmc"]


@dataclass(frozen=True)
class Candidate:
    id: str
    source: Source
    url: str
    host: str
    # publishedVersion, acceptedVersion or submittedVersion, as Unpaywall says.
    version: str | None = None
    license: str | None = None


class FetchError(Exception):
    """The copy could not be fetched; the message is safe to show."""


def _candidate(source: Source, url: str, version: str | None, license: str | None) -> Candidate:
    digest = hashlib.sha256(url.encode()).hexdigest()[:12]
    return Candidate(
        id=digest,
        source=source,
        url=url,
        host=urlsplit(url).hostname or "",
        version=version,
        license=license,
    )


async def find(
    http: httpx.AsyncClient,
    *,
    doi: str | None,
    pmcid: str | None,
    email: str | None,
) -> list[Candidate]:
    """Open-access PDFs for this record, the most authoritative first."""
    found: list[Candidate] = []
    if pmcid:
        found += await _pmc(http, pmcid)
    if doi and email:
        found += await _unpaywall(http, doi, email)
    unique: dict[str, Candidate] = {}
    for candidate in found:
        unique.setdefault(candidate.url, candidate)
    return list(unique.values())


async def _unpaywall(http: httpx.AsyncClient, doi: str, email: str) -> list[Candidate]:
    try:
        response = await http.get(
            UNPAYWALL.format(doi=quote(doi, safe="/")),
            params={"email": email},
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.HTTPError:
        return []
    if response.status_code != 200:
        return []
    try:
        data = response.json()
    except ValueError:
        return []
    locations = data.get("oa_locations") or []
    if not isinstance(locations, list):
        return []
    found = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        url = location.get("url_for_pdf")
        if isinstance(url, str) and url.startswith("https://"):
            found.append(
                _candidate(
                    "unpaywall",
                    url,
                    location.get("version") if isinstance(location.get("version"), str) else None,
                    location.get("license") if isinstance(location.get("license"), str) else None,
                )
            )
    return found


async def _pmc(http: httpx.AsyncClient, pmcid: str) -> list[Candidate]:
    """PMC publishes each open-access article as `PMCnnn.v/PMCnnn.v.pdf` in a public bucket;
    the latest version is the one to fetch."""
    number = re.fullmatch(r"(?i)pmc(\d{1,10})", pmcid.strip())
    if not number:
        return []
    prefix = f"PMC{number.group(1)}."
    try:
        response = await http.get(
            f"{PMC_BUCKET}/",
            params={"list-type": "2", "prefix": prefix, "max-keys": "100"},
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.HTTPError:
        return []
    if response.status_code != 200:
        return []
    try:
        root = ElementTree.fromstring(response.content)
    except ElementTree.ParseError:
        return []
    keys = [node.text or "" for node in root.iter(f"{S3}Key")]
    pdfs = [key for key in keys if re.fullmatch(rf"{re.escape(prefix)}\d+/.+\.pdf", key)]
    if not pdfs:
        return []
    latest = max(pdfs, key=lambda key: int(key[len(prefix) :].split("/", 1)[0]))
    return [_candidate("pmc", f"{PMC_BUCKET}/{latest}", "publishedVersion", None)]


async def download(http: httpx.AsyncClient, url: str, *, limit: int) -> bytes:
    for _ in range(MAX_REDIRECTS + 1):
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname:
            raise FetchError("Only https links are followed.")
        await _require_public(parts.hostname, parts.port or 443)
        try:
            async with http.stream(
                "GET", url, timeout=TIMEOUT_SECONDS, follow_redirects=False
            ) as response:
                _check_peer(response)
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                if response.status_code != 200:
                    raise FetchError(f"The site answered {response.status_code}.")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > limit:
                        raise FetchError("The file is larger than this Winnow accepts.")
                return bytes(body)
        except httpx.HTTPError as error:
            raise FetchError("The site could not be reached.") from error
    raise FetchError("The link redirected too many times.")


async def _require_public(host: str, port: int) -> None:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as error:
        raise FetchError("The site's address could not be found.") from error
    for *_, address in infos:
        if not ipaddress.ip_address(address[0]).is_global:
            raise FetchError("That address is not on the public internet.")


def _check_peer(response: httpx.Response) -> None:
    """The address really connected to, in case the name resolved differently the second
    time (DNS rebinding)."""
    stream = response.extensions.get("network_stream")
    peer = stream.get_extra_info("server_addr") if stream is not None else None
    if peer and not ipaddress.ip_address(peer[0]).is_global:
        raise FetchError("That address is not on the public internet.")
