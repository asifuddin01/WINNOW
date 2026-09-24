"""The clamd client, against a stand-in clamd that speaks INSTREAM (guide 12.4)."""

import asyncio
import struct
from collections.abc import AsyncIterator

import pytest

from app.security import clamav
from tests.pdf_helpers import EICAR


class FakeClamd:
    """Reads INSTREAM chunks like clamd and flags the EICAR string."""

    def __init__(self, reply: bytes | None = None) -> None:
        self.reply = reply
        self.received = b""
        self.chunk_sizes: list[int] = []

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        command = await reader.readuntil(b"\0")
        if command == b"zPING\0":
            writer.write(b"PONG\0")
        else:
            assert command == b"zINSTREAM\0"
            while True:
                (size,) = struct.unpack(">I", await reader.readexactly(4))
                if size == 0:
                    break
                self.chunk_sizes.append(size)
                self.received += await reader.readexactly(size)
            if self.reply is not None:
                writer.write(self.reply)
            elif EICAR in self.received:
                writer.write(b"stream: Eicar-Test-Signature FOUND\0")
            else:
                writer.write(b"stream: OK\0")
        await writer.drain()
        writer.close()


async def serve(clamd: FakeClamd) -> tuple[asyncio.Server, int]:
    server = await asyncio.start_server(clamd.handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


async def test_a_clean_file_and_an_infected_one() -> None:
    clamd = FakeClamd()
    server, port = await serve(clamd)
    async with server:
        assert await clamav.scan("127.0.0.1", port, [b"%PDF-1.4 fine"]) == clamav.ScanResult(True)
        found = await clamav.scan("127.0.0.1", port, [b"%PDF-1.4 ", EICAR])
        assert found == clamav.ScanResult(False, "Eicar-Test-Signature")


async def test_large_files_go_in_chunks_clamd_accepts() -> None:
    clamd = FakeClamd()
    server, port = await serve(clamd)

    async def source() -> AsyncIterator[bytes]:
        yield bytes(clamav.CHUNK * 2 + 10)
        yield b"tail"

    async with server:
        assert (await clamav.scan("127.0.0.1", port, source())).clean
    assert clamd.chunk_sizes == [clamav.CHUNK, clamav.CHUNK, 10, 4]
    assert len(clamd.received) == clamav.CHUNK * 2 + 14


async def test_ping() -> None:
    server, port = await serve(FakeClamd())
    async with server:
        assert await clamav.ping("127.0.0.1", port)
    assert not await clamav.ping("127.0.0.1", port, within=0.5)


@pytest.mark.parametrize(
    "reply",
    [b"INSTREAM size limit exceeded. ERROR\0", b"stream: lstat() failed ERROR\0"],
)
async def test_an_error_is_not_a_verdict(reply: bytes) -> None:
    server, port = await serve(FakeClamd(reply))
    async with server:
        with pytest.raises(clamav.ScannerUnavailableError):
            await clamav.scan("127.0.0.1", port, [b"%PDF-"])


async def test_no_scanner_is_unavailable_not_clean() -> None:
    server, port = await serve(FakeClamd())
    server.close()
    await server.wait_closed()
    with pytest.raises(clamav.ScannerUnavailableError):
        await clamav.scan("127.0.0.1", port, [b"%PDF-"], within=1)


async def test_a_scanner_that_never_answers_times_out() -> None:
    async def silent(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.read()  # everything, until the client gives up and hangs up
        writer.close()

    server = await asyncio.start_server(silent, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        with pytest.raises(clamav.ScannerUnavailableError):
            await clamav.scan("127.0.0.1", port, [b"%PDF-"], within=0.2)


def test_parse_reply() -> None:
    assert clamav.parse_reply("stream: OK") == clamav.ScanResult(True)
    assert clamav.parse_reply("stream: Win.Test.EICAR_HDB-1 FOUND") == clamav.ScanResult(
        False, "Win.Test.EICAR_HDB-1"
    )
    with pytest.raises(clamav.ScannerUnavailableError):
        clamav.parse_reply("garbage")
