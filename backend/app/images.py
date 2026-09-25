"""SVG to PNG and PDF for downloads: the PRISMA diagram (guide 8.14, PNG at 300 dpi) and the
risk-of-bias plots (8.13).

The SVGs are Winnow's own, built from escaped text. CairoSVG still runs in its safe mode,
which fetches nothing and resolves no XML entities, and in a thread, since rendering is
CPU work.
"""

import asyncio
import struct
import zlib

import cairosvg

PRINT_DPI = 300
INCH = 0.0254  # metres


def _png(svg: str, dpi: int) -> bytes:
    data: bytes = cairosvg.svg2png(bytestring=svg.encode(), dpi=dpi, unsafe=False)
    return with_resolution(data, dpi)


def with_resolution(png: bytes, dpi: int) -> bytes:
    """The PNG with its resolution written in (a `pHYs` chunk after the header). CairoSVG
    draws the pixels for the resolution asked but does not say so, and a word processor
    then places a 300-dpi figure at four times its size."""
    per_metre = round(dpi / INCH)
    body = b"pHYs" + struct.pack(">IIB", per_metre, per_metre, 1)
    chunk = struct.pack(">I", 9) + body + struct.pack(">I", zlib.crc32(body))
    header_end = 8 + 8 + 13 + 4  # signature, then IHDR's length, type, data and CRC
    return png[:header_end] + chunk + png[header_end:]


def _pdf(svg: str) -> bytes:
    data: bytes = cairosvg.svg2pdf(bytestring=svg.encode(), unsafe=False)
    return data


async def svg_to_png(svg: str, *, dpi: int = PRINT_DPI) -> bytes:
    return await asyncio.to_thread(_png, svg, dpi)


async def svg_to_pdf(svg: str) -> bytes:
    return await asyncio.to_thread(_pdf, svg)
