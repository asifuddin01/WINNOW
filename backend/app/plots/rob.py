"""Risk-of-bias plots as SVG (guide 8.13): the traffic-light table and the summary bars.

The colours are robvis's, which reviewers know from published reviews; every judgement
also has a symbol and a word in the legend, so none depends on colour alone (guide 14).
Newcastle-Ottawa stars are shown as counts, with no risk colours: the scale defines no
conversion to risk. Every piece of text is escaped; the SVG holds no scripts or links.
"""

from xml.sax.saxutils import escape, quoteattr

from app import rob
from app.schemas.rob import DomainSummaryOut, StudyRow

FONT = "DejaVu Sans, Helvetica, Arial, sans-serif"
INK = "#1f2933"
MUTED = "#52606d"
LINE = "#cbd2d9"

MINUS, TIMES, DASH = "\u2212", "\u00d7", "\u2013"
# judgement → (fill, symbol, ink on the fill)
STYLE: dict[str, tuple[str, str, str]] = {
    "low": ("#02C100", "+", "#ffffff"),
    "some_concerns": ("#E2DF07", MINUS, INK),
    "moderate": ("#E2DF07", MINUS, INK),
    "high": ("#BF0000", TIMES, "#ffffff"),
    "serious": ("#BF0000", TIMES, "#ffffff"),
    "critical": ("#820000", "!", "#ffffff"),
    "unclear": ("#4EA1F7", "?", INK),
    "no_information": ("#4EA1F7", "?", INK),
}
STARS = ("#eef2f7", "#d9e2ec", "#bcccdc", "#9fb3c8", "#829ab1")


def _style(judgement: str) -> tuple[str, str, str]:
    if judgement.startswith("stars_"):
        count = int(judgement.removeprefix("stars_") or 0)
        return STARS[min(count, len(STARS) - 1)], f"{count}★", INK
    return STYLE.get(judgement, ("#9aa5b1", "?", INK))


def _text(
    x: float,
    y: float,
    value: str,
    *,
    size: int = 12,
    anchor: str = "start",
    fill: str = INK,
    weight: str = "normal",
) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" '
        f'fill="{fill}" font-weight="{weight}">{escape(value)}</text>'
    )


def _wrap(document: list[str], width: float, height: float, title: str, desc: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" role="img" font-family={quoteattr(FONT)} '
        'aria-labelledby="rob-title rob-desc">'
        f'<title id="rob-title">{escape(title)}</title><desc id="rob-desc">{escape(desc)}</desc>'
        f'<rect width="100%" height="100%" fill="#ffffff"/>{"".join(document)}</svg>'
    )


def _columns(variant: rob.TemplateVariant) -> list[tuple[str, str]]:
    """(cell key, name) for every judged domain axis, in the tool's order."""
    columns = []
    for domain in variant.domains:
        for axis in domain.judgement_axes:
            suffix = f" ({axis.name.lower()})" if len(domain.judgement_axes) > 1 else ""
            columns.append((f"{domain.key}.{axis.key}", f"{domain.name}{suffix}"))
    return columns


def _judgement_names(variant: rob.TemplateVariant) -> dict[str, str]:
    return {
        choice.key: choice.label
        for domain in variant.domains
        for axis in domain.judgement_axes
        for choice in axis.allowed_judgements
    }


def traffic_light(
    template: rob.ToolTemplate, variant: rob.TemplateVariant, studies: list[StudyRow]
) -> str:
    columns = _columns(variant)
    with_overall = any(study.overall for study in studies)
    names = _judgement_names(variant)
    label_width, cell, top = 190.0, 36.0, 64.0
    grid_left = label_width + 10
    count = len(columns) + (1 if with_overall else 0)
    legend_top = top + cell * max(len(studies), 1) + 24
    used = sorted(
        {judgement for study in studies for judgement in study.cells.values()}
        | ({study.overall for study in studies if study.overall} if with_overall else set()),
        key=lambda key: list(names).index(key) if key in names else 99,
    )
    key_lines = len(columns) + 1 + len(used)
    width = max(grid_left + cell * count + 20, 560.0)
    height = legend_top + 18 * key_lines + 30
    parts = [_text(16, 26, f"{template.name}: risk of bias per study", size=15, weight="bold")]
    for index in range(count):
        label = f"D{index + 1}" if index < len(columns) else "Overall"
        parts.append(
            _text(
                grid_left + cell * index + cell / 2, top - 12, label, anchor="middle", weight="bold"
            )
        )
    for row, study in enumerate(studies):
        y = top + cell * row
        parts.append(_text(16, y + cell / 2 + 4, study.label[:28]))
        parts.append(
            f'<line x1="16" x2="{width - 16:.1f}" y1="{y + cell:.1f}" '
            f'y2="{y + cell:.1f}" stroke="{LINE}"/>'
        )
        values = [study.cells.get(key) for key, _ in columns]
        if with_overall:
            values.append(study.overall)
        for column, judgement in enumerate(values):
            cx = grid_left + cell * column + cell / 2
            cy = y + cell / 2
            if judgement is None:
                parts.append(_text(cx, cy + 4, DASH, anchor="middle", fill=MUTED))
                continue
            fill, symbol, ink = _style(judgement)
            parts.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="13" fill="{fill}" '
                f'stroke="{INK}" stroke-opacity="0.25"/>'
            )
            parts.append(
                _text(
                    cx,
                    cy + 4.5,
                    symbol,
                    size=13 if len(symbol) == 1 else 10,
                    anchor="middle",
                    fill=ink,
                    weight="bold",
                )
            )
    if not studies:
        parts.append(_text(16, top + 20, "No submitted assessments yet.", fill=MUTED))
    y = legend_top
    for index, (_, name) in enumerate(columns):
        parts.append(_text(16, y, f"D{index + 1}: {name}", size=11, fill=MUTED))
        y += 18
    y += 6
    for judgement in used:
        fill, symbol, _ = _style(judgement)
        parts.append(
            f'<circle cx="24" cy="{y - 4:.1f}" r="7" fill="{fill}" stroke="{INK}" '
            'stroke-opacity="0.25"/>'
        )
        parts.append(_text(38, y, f"{symbol}  {names.get(judgement, judgement)}", size=11))
        y += 18
    desc = (
        f"Traffic-light plot of {len(studies)} studies assessed with {template.name} "
        f"({template.version}), {variant.name}. "
        + " ".join(
            f"{study.label}: "
            + ", ".join(
                f"D{index + 1} {names.get(study.cells[key], study.cells[key])}"
                for index, (key, _) in enumerate(columns)
                if key in study.cells
            )
            + "."
            for study in studies
        )
    )
    return _wrap(parts, width, height, f"{template.name}: risk of bias per study", desc)


def summary_bars(
    template: rob.ToolTemplate, variant: rob.TemplateVariant, domains: list[DomainSummaryOut]
) -> str:
    label_width, bar_width, bar, gap, top = 300.0, 360.0, 22.0, 12.0, 58.0
    width = label_width + bar_width + 60
    judgements: list[tuple[str, str]] = []
    for domain in domains:
        for count in domain.counts:
            if (count.judgement, count.label) not in judgements:
                judgements.append((count.judgement, count.label))
    legend_top = top + (bar + gap) * max(len(domains), 1) + 16
    height = legend_top + 18 * len(judgements) + 40
    title = f"{template.name}: risk of bias across studies"
    parts = [_text(16, 26, title, size=15, weight="bold")]
    for row, domain in enumerate(domains):
        y = top + (bar + gap) * row
        name = domain.domain_name + (
            f" ({domain.axis_name.lower()})" if domain.axis_key != "risk_of_bias" else ""
        )
        parts.append(_text(16, y + bar / 2 + 4, name[:44], size=11))
        x = label_width
        for count in domain.counts:
            if not count.count or not domain.total:
                continue
            share = count.count / domain.total
            fill, symbol, ink = _style(count.judgement)
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width * share:.1f}" '
                f'height="{bar:.1f}" fill="{fill}"/>'
            )
            if bar_width * share >= 34:
                parts.append(
                    _text(
                        x + bar_width * share / 2,
                        y + bar / 2 + 4,
                        f"{round(share * 100)}%",
                        size=10,
                        anchor="middle",
                        fill=ink,
                    )
                )
            x += bar_width * share
        parts.append(
            f'<rect x="{label_width:.1f}" y="{y:.1f}" width="{bar_width:.1f}" '
            f'height="{bar:.1f}" fill="none" stroke="{INK}" stroke-opacity="0.3"/>'
        )
    if not domains:
        parts.append(_text(16, top + 16, "No submitted assessments yet.", fill=MUTED))
    for tick in (0, 25, 50, 75, 100):
        x = label_width + bar_width * tick / 100
        parts.append(_text(x, legend_top - 4, f"{tick}%", size=9, anchor="middle", fill=MUTED))
    y = legend_top + 20
    for judgement, label in judgements:
        fill, symbol, _ = _style(judgement)
        parts.append(f'<rect x="16" y="{y - 10:.1f}" width="14" height="12" fill="{fill}"/>')
        parts.append(_text(38, y, f"{symbol}  {label}", size=11))
        y += 18
    studies = domains[0].total if domains else 0
    desc = (
        f"Share of {studies} studies at each judgement, per domain, {template.name} "
        f"({template.version}), {variant.name}. "
        + " ".join(
            f"{domain.domain_name}: "
            + ", ".join(f"{count.label} {count.count}" for count in domain.counts)
            + "."
            for domain in domains
        )
    )
    return _wrap(parts, width, height, title, desc)
