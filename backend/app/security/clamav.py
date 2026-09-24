"""Virus scanning with clamd over its INSTREAM protocol (guide 12.4).

No client library: the protocol is a command, the file in length-prefixed chunks, and a
one-line answer. `stream: OK` is clean; `stream: <signature> FOUND` is infected; anything
else, or no answer, is an error, and the file stays unavailable until a scan succeeds.
"""

import asyncio
import struct
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass

CHUNK = 256 * 1024
TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True)
class ScanResult:
    clean: bool
    # The signature clamd matched, when it found one.
    signature: str | None = None


class ScannerUnavailableError(Exception):
    """clamd could not be reached or did not give an answer."""


async def scan(
    host: str,
    port: int,
    chunks: AsyncIterator[bytes] | Iterable[bytes],
    *,
    within: float = TIMEOUT_SECONDS,
) -> ScanResult:
    try:
        return await asyncio.wait_for(_scan(host, port, chunks), within)
    except (OSError, TimeoutError, asyncio.IncompleteReadError) as error:
        raise ScannerUnavailableError(str(error) or type(error).__name__) from error


async def _scan(host: str, port: int, chunks: AsyncIterator[bytes] | Iterable[bytes]) -> ScanResult:
    reader, writer = await asyncio.open_connection(host, port)
    try:
        writer.write(b"zINSTREAM\0")
        async for chunk in _pieces(chunks):
            writer.write(struct.pack(">I", len(chunk)) + chunk)
            await writer.drain()
        writer.write(struct.pack(">I", 0))
        await writer.drain()
        reply = (await reader.readuntil(b"\0")).rstrip(b"\0").decode("utf-8", "replace")
    finally:
        writer.close()
        await writer.wait_closed()
    return parse_reply(reply)


def parse_reply(reply: str) -> ScanResult:
    """`stream: OK` / `stream: Eicar-Signature FOUND` / `... ERROR`."""
    answer = reply.split(":", 1)[-1].strip()
    if answer == "OK":
        return ScanResult(clean=True)
    if answer.endswith(" FOUND"):
        return ScanResult(clean=False, signature=answer.removesuffix(" FOUND").strip())
    raise ScannerUnavailableError(f"clamd answered: {reply}")


async def ping(host: str, port: int, *, within: float = 5.0) -> bool:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), within)
    except (OSError, TimeoutError):
        return False
    try:
        writer.write(b"zPING\0")
        await writer.drain()
        reply = await asyncio.wait_for(reader.readuntil(b"\0"), within)
        return reply.rstrip(b"\0") == b"PONG"
    except (OSError, TimeoutError, asyncio.IncompleteReadError):
        return False
    finally:
        writer.close()
        await writer.wait_closed()


async def _pieces(chunks: AsyncIterator[bytes] | Iterable[bytes]) -> AsyncIterator[bytes]:
    """The file in pieces clamd accepts, whatever size the source hands them over in."""
    if isinstance(chunks, AsyncIterator):
        async for chunk in chunks:
            for start in range(0, len(chunk), CHUNK):
                yield chunk[start : start + CHUNK]
    else:
        for chunk in chunks:
            for start in range(0, len(chunk), CHUNK):
                yield chunk[start : start + CHUNK]
