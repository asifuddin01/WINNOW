"""Accessible, deterministic SVG rendering for calculated PRISMA counts."""

import textwrap
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from app.prisma.types import PrismaCounts

_SVG_NAMESPACE = "http://www.w3.org/2000/svg"
_XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
_WIDTH = 1200
_MAIN_X = 150
_MAIN_WIDTH = 520
_SIDE_X = 760
_SIDE_WIDTH = 390
_BOX_PADDING = 24
_FONT_SIZE = 17
_LINE_HEIGHT = 25
_MIN_BOX_HEIGHT = 78
_ROW_GAP = 54
_SECTION_HEIGHT = 42
_SECTION_GAP = 18


@dataclass(frozen=True, slots=True)
class _Line:
    text: str
    bold: bool


@dataclass(frozen=True, slots=True)
class _Box:
    x: int
    y: int
    width: int
    height: int
    lines: tuple[_Line, ...]

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def centre_x(self) -> int:
        return self.x + self.width // 2

    @property
    def centre_y(self) -> int:
        return self.y + self.height // 2


def _wrapped_parts(line: str, width: int) -> tuple[str, ...]:
    marker = line.rfind(" (n = ")
    suffix = line[marker + 1 :] if marker >= 0 else ""
    if marker < 0 or not suffix.rstrip(":").endswith(")"):
        return tuple(
            textwrap.wrap(
                line,
                width=width,
                break_long_words=True,
                break_on_hyphens=False,
                replace_whitespace=True,
            )
            or ("",)
        )

    # Keeping the generated count suffix whole avoids visually orphaning its equals sign.
    label_parts = list(
        textwrap.wrap(
            line[:marker],
            width=width,
            break_long_words=True,
            break_on_hyphens=False,
            replace_whitespace=True,
        )
    )
    if label_parts and len(label_parts[-1]) + len(suffix) + 1 <= width:
        label_parts[-1] = f"{label_parts[-1]} {suffix}"
    else:
        label_parts.append(suffix)
    return tuple(label_parts)


def _wrapped(lines: tuple[str, ...], width: int, bold_indices: frozenset[int]) -> tuple[_Line, ...]:
    wrapped: list[_Line] = []
    for index, line in enumerate(lines):
        parts = _wrapped_parts(line, width)
        wrapped.extend(_Line(text=part, bold=index in bold_indices) for part in parts)
    return tuple(wrapped)


def _box(
    x: int,
    y: int,
    width: int,
    lines: tuple[str, ...],
    *,
    bold_indices: frozenset[int] = frozenset({0}),
) -> _Box:
    # A full-width glyph is roughly one font-size wide; this prevents custom labels escaping.
    character_width = max(1, (width - 2 * _BOX_PADDING) // _FONT_SIZE)
    wrapped = _wrapped(lines, character_width, bold_indices)
    height = max(_MIN_BOX_HEIGHT, 2 * _BOX_PADDING + len(wrapped) * _LINE_HEIGHT)
    return _Box(x=x, y=y, width=width, height=height, lines=wrapped)


def _source_lines(counts: PrismaCounts) -> tuple[str, ...]:
    lines: list[str] = ["Records identified from databases and registers:"]
    lines.extend(f"{source.name} (n = {source.count})" for source in counts.database_sources)
    if counts.other_sources:
        lines.append("Records identified through other methods:")
        lines.extend(f"{source.name} (n = {source.count})" for source in counts.other_sources)
    lines.append(f"Total records identified (n = {counts.records_identified_total})")
    return tuple(lines)


def _reason_lines(counts: PrismaCounts) -> tuple[str, ...]:
    lines: list[str] = [f"Reports excluded (n = {counts.reports_excluded_total}):"]
    lines.extend(
        f"{item.reason} (n = {item.count})" for item in counts.reports_excluded_with_reasons
    )
    return tuple(lines)


def _description(counts: PrismaCounts) -> str:
    databases = (
        "; ".join(f"{source.name}: {source.count}" for source in counts.database_sources)
        or "none: 0"
    )
    other_sources = (
        "; ".join(f"{source.name}: {source.count}" for source in counts.other_sources) or "none: 0"
    )
    reasons = (
        "; ".join(f"{item.reason}: {item.count}" for item in counts.reports_excluded_with_reasons)
        or "none: 0"
    )
    return (
        "PRISMA flow summary. "
        f"Database and register records total: {counts.records_identified_from_databases}. "
        f"Database and register records by source: {databases}. "
        f"Other-source records total: {counts.records_identified_from_other_sources}. "
        f"Other-source records by source: {other_sources}. "
        f"Total records identified: {counts.records_identified_total}. "
        f"Duplicates removed: {counts.duplicates_removed}. "
        f"Records removed for other reasons: {counts.records_removed_other_reasons}. "
        f"Records screened: {counts.records_screened}. "
        f"Records excluded: {counts.records_excluded}. "
        f"Reports sought for retrieval: {counts.reports_sought}. "
        f"Reports not retrieved: {counts.reports_not_retrieved}. "
        f"Reports assessed for eligibility: {counts.reports_assessed}. "
        f"Reports excluded: {counts.reports_excluded_total}. "
        f"Primary exclusion reasons: {reasons}. "
        f"Studies included in review: {counts.studies_included}."
    )


def _add_phase(svg: ET.Element, y: int, label: str) -> None:
    ET.SubElement(
        svg,
        "rect",
        {
            "x": "40",
            "y": str(y),
            "width": "1110",
            "height": str(_SECTION_HEIGHT),
            "rx": "6",
            "fill": "#0F766E",
        },
    )
    text = ET.SubElement(
        svg,
        "text",
        {
            "x": "64",
            "y": str(y + 28),
            "fill": "#FFFFFF",
            "font-family": "sans-serif",
            "font-size": "22",
            "font-weight": "700",
        },
    )
    text.text = label


def _draw_box(svg: ET.Element, box: _Box) -> None:
    group = ET.SubElement(svg, "g")
    ET.SubElement(
        group,
        "rect",
        {
            "x": str(box.x),
            "y": str(box.y),
            "width": str(box.width),
            "height": str(box.height),
            "rx": "8",
            "fill": "#FFFFFF",
            "stroke": "#1F2937",
            "stroke-width": "2",
        },
    )
    baseline = box.y + _BOX_PADDING + _FONT_SIZE
    for index, line in enumerate(box.lines):
        text = ET.SubElement(
            group,
            "text",
            {
                "x": str(box.x + _BOX_PADDING),
                "y": str(baseline + index * _LINE_HEIGHT),
                "fill": "#111827",
                "font-family": "sans-serif",
                "font-size": str(_FONT_SIZE),
                "font-weight": "700" if line.bold else "400",
            },
        )
        text.text = line.text


def _vertical_arrow(svg: ET.Element, upper: _Box, lower: _Box) -> None:
    end_y = lower.y - 2
    ET.SubElement(
        svg,
        "line",
        {
            "x1": str(upper.centre_x),
            "y1": str(upper.bottom + 2),
            "x2": str(lower.centre_x),
            "y2": str(end_y - 10),
            "stroke": "#334155",
            "stroke-width": "3",
        },
    )
    ET.SubElement(
        svg,
        "polygon",
        {
            "points": (
                f"{lower.centre_x},{end_y} "
                f"{lower.centre_x - 7},{end_y - 12} "
                f"{lower.centre_x + 7},{end_y - 12}"
            ),
            "fill": "#334155",
        },
    )


def _side_arrow(svg: ET.Element, main: _Box, side: _Box) -> None:
    bend_x = main.right + (side.x - main.right) // 2
    end_x = side.x - 2
    points = (
        f"{main.right + 2},{main.centre_y} "
        f"{bend_x},{main.centre_y} "
        f"{bend_x},{side.centre_y} "
        f"{end_x - 10},{side.centre_y}"
    )
    ET.SubElement(
        svg,
        "polyline",
        {
            "points": points,
            "fill": "none",
            "stroke": "#334155",
            "stroke-width": "3",
            "stroke-linejoin": "round",
        },
    )
    ET.SubElement(
        svg,
        "polygon",
        {
            "points": (
                f"{end_x},{side.centre_y} "
                f"{end_x - 12},{side.centre_y - 7} "
                f"{end_x - 12},{side.centre_y + 7}"
            ),
            "fill": "#334155",
        },
    )


def render_svg(counts: PrismaCounts) -> str:
    """Render calculated PRISMA counts as a standalone accessible SVG string.

    Input is a coherent ``PrismaCounts`` value; output is deterministic XML with semantic
    text, an accessible name and a full text alternative. Complexity is O(d + o + r + c)
    time and output space, where c is wrapped text length. This follows guide 9.4's subset:
    full PRISMA automation and updated-review branches are omitted because the guide defines
    no inputs for them, while manual other sources are combined into the identification box.
    """

    identification_y = 24
    source_lines = _source_lines(counts)
    source_heading_indices = {0, len(source_lines) - 1}
    if counts.other_sources:
        source_heading_indices.add(len(counts.database_sources) + 1)
    identified = _box(
        _MAIN_X,
        identification_y + _SECTION_HEIGHT + _SECTION_GAP,
        _MAIN_WIDTH,
        source_lines,
        bold_indices=frozenset(source_heading_indices),
    )
    removed = _box(
        _SIDE_X,
        identified.y,
        _SIDE_WIDTH,
        (
            "Records removed before screening:",
            f"Duplicate records removed (n = {counts.duplicates_removed})",
            (f"Records removed for other reasons (n = {counts.records_removed_other_reasons})"),
        ),
    )

    identification_bottom = max(identified.bottom, removed.bottom)
    screening_y = identification_bottom + _ROW_GAP
    screened = _box(
        _MAIN_X,
        screening_y + _SECTION_HEIGHT + _SECTION_GAP,
        _MAIN_WIDTH,
        (f"Records screened (n = {counts.records_screened})",),
    )
    records_excluded = _box(
        _SIDE_X,
        screened.y,
        _SIDE_WIDTH,
        (f"Records excluded (n = {counts.records_excluded})",),
    )

    sought_y = max(screened.bottom, records_excluded.bottom) + _ROW_GAP
    sought = _box(
        _MAIN_X,
        sought_y,
        _MAIN_WIDTH,
        (f"Reports sought for retrieval (n = {counts.reports_sought})",),
    )
    not_retrieved = _box(
        _SIDE_X,
        sought.y,
        _SIDE_WIDTH,
        (f"Reports not retrieved (n = {counts.reports_not_retrieved})",),
    )

    assessed_y = max(sought.bottom, not_retrieved.bottom) + _ROW_GAP
    assessed = _box(
        _MAIN_X,
        assessed_y,
        _MAIN_WIDTH,
        (f"Reports assessed for eligibility (n = {counts.reports_assessed})",),
    )
    reports_excluded = _box(
        _SIDE_X,
        assessed.y,
        _SIDE_WIDTH,
        _reason_lines(counts),
    )

    screening_bottom = max(assessed.bottom, reports_excluded.bottom)
    included_y = screening_bottom + _ROW_GAP
    included = _box(
        _MAIN_X,
        included_y + _SECTION_HEIGHT + _SECTION_GAP,
        _MAIN_WIDTH,
        (f"Studies included in review (n = {counts.studies_included})",),
    )
    footer_y = included.bottom + 42
    height = footer_y + 44

    svg = ET.Element(
        "svg",
        {
            "xmlns": _SVG_NAMESPACE,
            "viewBox": f"0 0 {_WIDTH} {height}",
            "width": str(_WIDTH),
            "height": str(height),
            "role": "img",
            "focusable": "false",
            "aria-labelledby": "prisma-title",
            "aria-describedby": "prisma-desc",
            "preserveAspectRatio": "xMidYMin meet",
            f"{{{_XML_NAMESPACE}}}lang": "en",
        },
    )
    title = ET.SubElement(svg, "title", {"id": "prisma-title"})
    title.text = "PRISMA 2020 flow diagram"
    description = ET.SubElement(svg, "desc", {"id": "prisma-desc"})
    description.text = _description(counts)
    metadata = ET.SubElement(svg, "metadata")
    metadata.text = (
        "Adapted from Page MJ et al. The PRISMA 2020 statement. BMJ 2021;372:n71. "
        "doi:10.1136/bmj.n71. Licensed CC BY 4.0: "
        "https://creativecommons.org/licenses/by/4.0/."
    )
    ET.SubElement(
        svg,
        "rect",
        {
            "x": "0",
            "y": "0",
            "width": str(_WIDTH),
            "height": str(height),
            "fill": "#FFFFFF",
        },
    )

    # Connectors are drawn first so phase labels and boxes remain visually uninterrupted.
    _vertical_arrow(svg, identified, screened)
    _side_arrow(svg, identified, removed)
    _vertical_arrow(svg, screened, sought)
    _side_arrow(svg, screened, records_excluded)
    _vertical_arrow(svg, sought, assessed)
    _side_arrow(svg, sought, not_retrieved)
    _vertical_arrow(svg, assessed, included)
    _side_arrow(svg, assessed, reports_excluded)

    _add_phase(svg, identification_y, "Identification")
    _add_phase(svg, screening_y, "Screening")
    _add_phase(svg, included_y, "Included")
    for box in (
        identified,
        removed,
        screened,
        records_excluded,
        sought,
        not_retrieved,
        assessed,
        reports_excluded,
        included,
    ):
        _draw_box(svg, box)

    footer = ET.SubElement(
        svg,
        "text",
        {
            "x": "600",
            "y": str(footer_y),
            "text-anchor": "middle",
            "fill": "#475569",
            "font-family": "sans-serif",
            "font-size": "14",
        },
    )
    footer.text = "Adapted from the PRISMA 2020 flow diagram (CC BY 4.0)."
    return ET.tostring(svg, encoding="unicode", short_empty_elements=True)
