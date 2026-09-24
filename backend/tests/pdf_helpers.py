"""Small, valid PDFs and ZIPs for the full-text tests, built in memory.

The EICAR test string is put together at run time so that no file in the repository is
itself flagged by a virus scanner.
"""

import io
import zipfile

from pypdf import PdfWriter

EICAR = "".join(
    ("X5O!P%@AP[4\\PZX54(P^)7CC)7}$", "EICAR-STANDARD-ANTIVIRUS-TEST-FILE!", "$H+H*")
).encode()


def tiny_pdf(*pages: str) -> bytes:
    """A PDF with one line of text per page, readable by pypdf and pdf.js."""
    texts = pages or ("Winnow full text",)
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",  # the page tree, filled in below
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    kids = []
    for text in texts:
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode()
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        content = len(objects)
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % content
        )
        kids.append(len(objects))
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % kid for kid in kids),
        len(kids),
    )
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    )
    return out.getvalue()


def eicar_pdf() -> bytes:
    """A real PDF carrying the EICAR test file as an attachment: guide 12.10's "malicious
    PDF". ClamAV unpacks the PDF and finds it; the bare EICAR file is not a PDF at all, and
    is refused at upload before it is stored."""
    writer = PdfWriter(clone_from=io.BytesIO(tiny_pdf("A paper with something attached")))
    writer.add_attachment("eicar.com", EICAR)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def make_zip(files: dict[str, bytes], *, level: int = 6) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=level) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return out.getvalue()


def zip_bomb(megabytes: int = 64) -> bytes:
    """One entry of zeros: a few kilobytes packed, `megabytes` unpacked."""
    out = io.BytesIO()
    with (
        zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z,
        z.open("paper.pdf", "w", force_zip64=True) as entry,
    ):
        block = bytes(1024 * 1024)
        for _ in range(megabytes):
            entry.write(block)
    return out.getvalue()
