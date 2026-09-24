"""Is it a PDF, and what does it say? (guide 12.4, 6.1 `text_extracted`, `page_count`).

A PDF is known by its magic bytes, `%PDF-`, which the format allows anywhere in the first
kilobyte. The text is read with pypdf for search and keyword highlighting; a PDF pypdf
cannot read is still kept and shown by the viewer, only without extracted text.
"""

import io
import logging
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PyPdfError

MAGIC = b"%PDF-"
MAGIC_WITHIN = 1024
# Enough for any paper; a 3,000-page scanned book is not read to the end.
MAX_TEXT_CHARS = 2_000_000
MAX_TEXT_PAGES = 500


@dataclass(frozen=True)
class PdfText:
    pages: int | None
    text: str | None


def looks_like_pdf(head: bytes) -> bool:
    return MAGIC in head[:MAGIC_WITHIN]


def read_text(data: bytes) -> PdfText:
    # pypdf warns about every malformed object through logging; they are not errors here.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            return PdfText(pages=None, text=None)
        pages = len(reader.pages)
        parts: list[str] = []
        size = 0
        for page in reader.pages[:MAX_TEXT_PAGES]:
            piece = page.extract_text() or ""
            parts.append(piece)
            size += len(piece)
            if size >= MAX_TEXT_CHARS:
                break
        # Postgres text cannot hold NUL, which some PDFs' text layers contain.
        text = "\n".join(parts).replace("\x00", "")[:MAX_TEXT_CHARS]
        return PdfText(pages=pages, text=text or None)
    except (PyPdfError, ValueError, KeyError, TypeError, RecursionError, OSError):
        return PdfText(pages=None, text=None)
