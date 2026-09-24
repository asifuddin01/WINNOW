"""Knowing a PDF, and reading its text (guide 12.4, 6.1)."""

from app.fulltext.pdf import looks_like_pdf, read_text
from tests.pdf_helpers import tiny_pdf


def test_magic_bytes_within_the_first_kilobyte() -> None:
    assert looks_like_pdf(b"%PDF-1.7\n")
    assert looks_like_pdf(b"\xef\xbb\xbf" + b" " * 900 + b"%PDF-1.4")
    assert not looks_like_pdf(b" " * 1024 + b"%PDF-1.4")
    assert not looks_like_pdf(b"MZ\x90\x00 an executable")
    assert not looks_like_pdf(b"<html>%PDF</html>")


def test_text_and_pages() -> None:
    text = read_text(tiny_pdf("Kidney (renal) stones", "Page two"))
    assert text.pages == 2
    assert text.text == "Kidney (renal) stones\nPage two"


def test_an_unreadable_pdf_is_kept_without_text() -> None:
    assert read_text(b"%PDF-1.4\nthis is not really a pdf").text is None
    assert read_text(b"%PDF-1.4\n" + bytes(64)).pages is None
