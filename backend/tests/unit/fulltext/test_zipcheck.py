"""Opening ZIPs of PDFs safely (guide 12.4): bombs, traversal, links, lies, Mac litter."""

import io
import stat
import zipfile

import pytest

from app.fulltext import zipcheck
from tests.pdf_helpers import make_zip, tiny_pdf, zip_bomb

LIMIT = 100 * 1024 * 1024


def test_pdfs_are_listed_and_everything_else_is_marked_skipped() -> None:
    data = make_zip(
        {
            "papers/Smith 2019.pdf": tiny_pdf(),
            "papers/notes.txt": b"hello",
            "__MACOSX/papers/._Smith 2019.pdf": b"\0\5\26\7",
            "papers/._Jones.pdf": b"\0\5\26\7",
            "papers/.DS_Store": b"\0",
        }
    )
    entries = zipcheck.inspect(io.BytesIO(data), max_entry_bytes=LIMIT)
    assert [(e.name, e.skip) for e in entries] == [
        ("Smith 2019.pdf", None),
        ("notes.txt", "not_pdf"),
        ("._Smith 2019.pdf", "system"),
        ("._Jones.pdf", "system"),
        (".DS_Store", "system"),
    ]
    first = entries[0]
    assert zipcheck.extract(io.BytesIO(data), first, limit=LIMIT) == tiny_pdf()


def test_a_zip_bomb_is_refused_before_anything_is_unpacked() -> None:
    with pytest.raises(zipcheck.ZipRejectedError, match="ZIP bomb"):
        zipcheck.inspect(io.BytesIO(zip_bomb(8)), max_entry_bytes=LIMIT)


def test_a_small_repetitive_file_is_not_mistaken_for_a_bomb() -> None:
    data = make_zip({"blank.pdf": b"%PDF-1.4\n" + bytes(500_000)}, level=9)
    [entry] = zipcheck.inspect(io.BytesIO(data), max_entry_bytes=LIMIT)
    assert entry.skip is None


@pytest.mark.parametrize(
    "name", ["../evil.pdf", "/etc/passwd.pdf", "a/../../b.pdf", "C:/win.pdf", "..\\x.pdf"]
)
def test_names_that_leave_the_folder_are_refused(name: str) -> None:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(zipfile.ZipInfo(name), tiny_pdf())
    with pytest.raises(zipcheck.ZipRejectedError, match="outside the folder"):
        zipcheck.inspect(io.BytesIO(out.getvalue()), max_entry_bytes=LIMIT)


def test_symlinks_are_refused() -> None:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        info = zipfile.ZipInfo("link.pdf")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(info, "/etc/passwd")
    with pytest.raises(zipcheck.ZipRejectedError, match="link"):
        zipcheck.inspect(io.BytesIO(out.getvalue()), max_entry_bytes=LIMIT)


def test_too_many_files_or_too_much_in_all() -> None:
    many = make_zip({f"{n}.pdf": b"%PDF-" for n in range(12)})
    with pytest.raises(zipcheck.ZipRejectedError, match="at most 10"):
        zipcheck.inspect(io.BytesIO(many), max_entry_bytes=LIMIT, max_entries=10)
    with pytest.raises(zipcheck.ZipRejectedError, match="more than"):
        zipcheck.inspect(io.BytesIO(many), max_entry_bytes=LIMIT, max_total_bytes=40)
    assert len(zipcheck.inspect(io.BytesIO(many), max_entry_bytes=LIMIT)) == 12


def test_not_a_zip() -> None:
    with pytest.raises(zipcheck.ZipRejectedError, match="not a ZIP"):
        zipcheck.inspect(io.BytesIO(b"%PDF-1.4 not a zip"), max_entry_bytes=LIMIT)


def test_oversized_and_encrypted_entries_are_skipped() -> None:
    data = make_zip({"big.pdf": tiny_pdf() * 20})
    [entry] = zipcheck.inspect(io.BytesIO(data), max_entry_bytes=100)
    assert entry.skip == "too_large"
    raw = bytearray(make_zip({"locked.pdf": tiny_pdf()}))
    # Set the "encrypted" flag in the central directory entry.
    central = raw.rindex(b"PK\x01\x02")
    raw[central + 8] |= 0x1
    [locked] = zipcheck.inspect(io.BytesIO(bytes(raw)), max_entry_bytes=LIMIT)
    assert locked.skip == "encrypted"


def test_an_entry_that_unpacks_to_more_than_it_declared_is_stopped() -> None:
    data = make_zip({"paper.pdf": tiny_pdf()})
    [entry] = zipcheck.inspect(io.BytesIO(data), max_entry_bytes=LIMIT)
    lying = zipcheck.Entry(entry.index, entry.path, entry.name, size=100)
    with pytest.raises(zipcheck.ZipRejectedError, match="more than it says"):
        zipcheck.extract(io.BytesIO(data), lying, limit=LIMIT)
    with pytest.raises(zipcheck.ZipRejectedError):
        zipcheck.extract(io.BytesIO(data), entry, limit=100)
    renamed = zipcheck.Entry(entry.index, "other.pdf", entry.name, size=entry.size)
    with pytest.raises(zipcheck.ZipRejectedError, match="changed"):
        zipcheck.extract(io.BytesIO(data), renamed, limit=LIMIT)
