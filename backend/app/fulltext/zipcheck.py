"""Opening a ZIP of PDFs without letting it open us (guide 12.4).

A ZIP is refused outright, before anything is extracted, when its central directory shows a
bomb (an entry that expands more than MAX_RATIO times, or more than MAX_TOTAL_BYTES in all),
more than MAX_ENTRIES files, or a name that could land outside the folder it is unpacked in
(absolute, a drive letter, "..", a NUL, a symlink). Extraction then counts the bytes it
really gets, because the sizes in a ZIP's headers can lie.

Mac Finder adds `__MACOSX/` and `._name` copies to every ZIP it makes; they are skipped.
"""

import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal

MAX_ENTRIES = 1_000
MAX_TOTAL_BYTES = 2 * 1024**3
# A PDF compresses a little; a bomb compresses by thousands. Checked on entries over 1 MB so
# a tiny, very repetitive file is not mistaken for one.
MAX_RATIO = 100
RATIO_FROM_BYTES = 1024 * 1024
READ_CHUNK = 1024 * 1024

Skip = Literal["not_pdf", "too_large", "encrypted", "system"]


@dataclass(frozen=True)
class Entry:
    index: int
    path: str
    name: str
    size: int
    skip: Skip | None = None


class ZipRejectedError(Exception):
    """This ZIP is not accepted; the message says why, in words for the uploader."""


def inspect(source: Path | BinaryIO, *, max_entry_bytes: int) -> list[Entry]:
    try:
        archive = zipfile.ZipFile(source)
    except (zipfile.BadZipFile, OSError) as error:
        raise ZipRejectedError("This is not a ZIP file Winnow can open.") from error
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ENTRIES:
            raise ZipRejectedError(
                f"The ZIP holds {len(infos):,} files; at most {MAX_ENTRIES:,} are accepted."
            )
        entries: list[Entry] = []
        total = 0
        for index, info in enumerate(infos):
            if unsafe_name(info.filename):
                raise ZipRejectedError(
                    "The ZIP contains a file whose name points outside the folder "
                    f"({info.filename[:80]!r}); it was not opened."
                )
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ZipRejectedError(
                    "The ZIP contains a link to another file; it was not opened."
                )
            if info.is_dir():
                continue
            total += info.file_size
            if total > MAX_TOTAL_BYTES:
                raise ZipRejectedError(
                    "The ZIP would unpack to more than "
                    f"{MAX_TOTAL_BYTES // 1024**3} GB; it was not opened."
                )
            if info.file_size > RATIO_FROM_BYTES and info.file_size > MAX_RATIO * max(
                info.compress_size, 1
            ):
                raise ZipRejectedError(
                    f"{_display(info.filename)} would unpack to "
                    f"{info.file_size // max(info.compress_size, 1):,} times its packed size: "
                    "this looks like a ZIP bomb, and the ZIP was not opened."
                )
            entries.append(
                Entry(
                    index=index,
                    path=info.filename,
                    name=_display(info.filename),
                    size=info.file_size,
                    skip=_skip(info, max_entry_bytes),
                )
            )
    return entries


def extract(source: Path | BinaryIO, entry: Entry, *, limit: int) -> bytes:
    """One entry's bytes, stopping as soon as it gives more than it declared or `limit`."""
    ceiling = min(entry.size, limit)
    with zipfile.ZipFile(source) as archive:
        info = archive.infolist()[entry.index]
        if info.filename != entry.path:
            raise ZipRejectedError("The ZIP changed while it was being read.")
        pieces: list[bytes] = []
        got = 0
        with archive.open(info) as member:
            while chunk := member.read(READ_CHUNK):
                got += len(chunk)
                if got > ceiling:
                    raise ZipRejectedError(
                        f"{entry.name} unpacks to more than it says it does; it was not opened."
                    )
                pieces.append(chunk)
    return b"".join(pieces)


def unsafe_name(name: str) -> bool:
    normalised = name.replace("\\", "/")
    if "\x00" in name or normalised.startswith("/") or re.match(r"^[A-Za-z]:", normalised):
        return True
    return ".." in normalised.split("/")


def _display(name: str) -> str:
    return name.replace("\\", "/").rsplit("/", 1)[-1]


def _skip(info: zipfile.ZipInfo, max_entry_bytes: int) -> Skip | None:
    name = info.filename.replace("\\", "/")
    base = name.rsplit("/", 1)[-1]
    if name.startswith("__MACOSX/") or base.startswith("._") or base == ".DS_Store":
        return "system"
    if not base.lower().endswith(".pdf"):
        return "not_pdf"
    if info.flag_bits & 0x1:
        return "encrypted"
    if info.file_size > max_entry_bytes:
        return "too_large"
    return None
