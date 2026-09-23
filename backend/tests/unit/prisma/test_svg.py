"""The PRISMA renderer emits deterministic, accessible and inert SVG XML."""

from dataclasses import replace
from xml.etree import ElementTree as ET

import pytest

from app.prisma import (
    ExclusionCount,
    PrismaCounts,
    PrismaInputs,
    SourceCount,
    counts,
    render_svg,
)

SVG_NS = "http://www.w3.org/2000/svg"
XML_NS = "http://www.w3.org/XML/1998/namespace"
ALLOWED_TAGS = {
    "desc",
    "g",
    "line",
    "metadata",
    "polygon",
    "polyline",
    "rect",
    "svg",
    "text",
    "title",
    "tspan",
}
FORBIDDEN_TAGS = {
    "a",
    "animate",
    "animateMotion",
    "animateTransform",
    "foreignObject",
    "image",
    "script",
    "set",
    "style",
    "use",
}


def local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1]


def parse_svg(result: str) -> ET.Element:
    # The input is generated locally by the pure renderer, never accepted from a user.
    return ET.fromstring(result)  # noqa: S314


def visible_text(root: ET.Element) -> str:
    return " ".join(" ".join(element.itertext()) for element in root.iter(f"{{{SVG_NS}}}text"))


def box_lines(root: ET.Element, heading: str) -> tuple[str, ...]:
    for group in root.findall(f"{{{SVG_NS}}}g"):
        lines = tuple(
            " ".join(element.itertext()) for element in group.findall(f"{{{SVG_NS}}}text")
        )
        if lines and heading in " ".join(lines):
            return lines
    raise AssertionError(f"No rendered box starts with {heading!r}")


def test_svg_is_parseable_and_accessibly_named(expected_counts: PrismaCounts) -> None:
    root = parse_svg(render_svg(expected_counts))

    assert root.tag == f"{{{SVG_NS}}}svg"
    assert root.attrib["role"] == "img"
    assert root.attrib["focusable"] == "false"
    assert root.attrib[f"{{{XML_NS}}}lang"] == "en"
    assert root.attrib["aria-labelledby"] == "prisma-title"
    assert root.attrib["aria-describedby"] == "prisma-desc"
    title = root.find(f"{{{SVG_NS}}}title")
    description = root.find(f"{{{SVG_NS}}}desc")
    assert title is not None
    assert title.attrib["id"] == "prisma-title"
    assert title.text
    assert description is not None
    assert description.attrib["id"] == "prisma-desc"
    assert description.text
    for expected in (
        "Database and register records total: 240",
        "MEDLINE: 120",
        "Other-source records total: 10",
        "Citation searching: 6",
        "Total records identified: 250",
        "Duplicates removed: 30",
        "Records removed for other reasons: 10",
        "Records screened: 210",
        "Records excluded: 150",
        "Reports sought for retrieval: 60",
        "Reports not retrieved: 5",
        "Reports assessed for eligibility: 55",
        "Reports excluded: 35",
        "Wrong population: 12",
        "Studies included in review: 20",
    ):
        assert expected in description.text

    view_box = [int(value) for value in root.attrib["viewBox"].split()]
    assert view_box[:2] == [0, 0]
    assert view_box[2] > 0
    assert view_box[3] > 0


def test_svg_contains_flow_labels_sources_reasons_and_counts(expected_counts: PrismaCounts) -> None:
    root = parse_svg(render_svg(expected_counts))
    text = visible_text(root)

    expected_text = (
        "Identification",
        "Screening",
        "Included",
        "MEDLINE",
        "Embase",
        "Citation searching",
        "Total records identified (n = 250)",
        "Duplicate records removed (n = 30)",
        "Records screened (n = 210)",
        "Records excluded (n = 150)",
        "Reports sought for retrieval (n = 60)",
        "Reports not retrieved (n = 5)",
        "Reports assessed for eligibility (n = 55)",
        "Reports excluded (n = 35)",
        "Wrong population",
        "Studies included in review (n = 20)",
    )
    for value in expected_text:
        assert value in text

    source_lines = box_lines(root, "Records identified from databases")
    assert source_lines.index("MEDLINE (n = 120)") < source_lines.index("Embase (n = 80)")
    assert source_lines.index("Embase (n = 80)") < source_lines.index("Cochrane CENTRAL (n = 40)")
    assert source_lines.index("Citation searching (n = 6)") < source_lines.index("Websites (n = 4)")
    reason_lines = box_lines(root, "Reports excluded")
    reason_text = " ".join(reason_lines)
    assert reason_text.index("Wrong population") < reason_text.index("Wrong intervention")


def test_svg_uses_only_inert_local_elements_and_attributes(expected_counts: PrismaCounts) -> None:
    result = render_svg(expected_counts)
    root = parse_svg(result)
    identifiers: list[str] = []

    for element in root.iter():
        tag_name = local_name(element.tag)
        assert tag_name in ALLOWED_TAGS
        assert tag_name not in FORBIDDEN_TAGS
        for attribute, value in element.attrib.items():
            name = local_name(attribute).casefold()
            assert not name.startswith("on")
            assert name != "href"
            assert "url(" not in value.casefold()
        if identifier := element.attrib.get("id"):
            identifiers.append(identifier)

    assert len(identifiers) == len(set(identifiers))
    lowered = result.casefold()
    assert "@import" not in lowered
    assert "@font-face" not in lowered
    assert 'font-family="sans-serif"' in result

    metadata = root.find(f"{{{SVG_NS}}}metadata")
    assert metadata is not None
    assert metadata.text
    assert "Page MJ et al." in metadata.text
    assert "CC BY 4.0" in metadata.text
    assert "https://creativecommons.org/licenses/by/4.0/" in metadata.text
    assert "Adapted from the PRISMA 2020 flow diagram" in " ".join(root.itertext())


class MaliciousInt(int):
    def __format__(self, format_spec: str) -> str:
        del format_spec
        return '</text><script onload="alert(2)">number</script>'


class MaliciousStr(str):
    def __format__(self, format_spec: str) -> str:
        del format_spec
        return "\x00"


def test_dynamic_labels_are_xml_escaped(prisma_inputs: PrismaInputs) -> None:
    payload = '</text><script onload="alert(1)">reason</script> & source'
    inputs = replace(
        prisma_inputs,
        database_sources=(
            SourceCount(name=payload, count=120),
            *prisma_inputs.database_sources[1:],
        ),
        full_text_exclusions=(ExclusionCount(reason=payload, count=35),),
    )

    result = render_svg(counts(inputs))
    root = parse_svg(result)

    assert payload in " ".join(root.itertext())
    assert "&lt;/text&gt;&lt;script" in result
    assert not any(local_name(element.tag) == "script" for element in root.iter())


def test_integer_subclasses_cannot_override_rendered_number_text() -> None:
    with pytest.raises(TypeError, match="must be an integer"):
        SourceCount(name="MEDLINE", count=MaliciousInt(120))


def test_string_subclasses_cannot_override_rendered_label_text() -> None:
    with pytest.raises(TypeError, match="must be a string"):
        SourceCount(name=MaliciousStr("MEDLINE"), count=120)


def test_svg_output_is_byte_for_byte_deterministic(expected_counts: PrismaCounts) -> None:
    assert render_svg(expected_counts) == render_svg(expected_counts)


def test_svg_with_zero_counts_still_parses() -> None:
    inputs = PrismaInputs(
        database_sources=(),
        other_sources=(),
        duplicates_removed=0,
        records_removed_other_reasons=0,
        non_duplicate_records=0,
        title_abstract_excluded=0,
        title_abstract_included=0,
        reports_not_retrieved=0,
        full_text_exclusions=(),
        full_text_included=0,
    )
    root = parse_svg(render_svg(counts(inputs)))
    assert "Total records identified (n = 0)" in " ".join(root.itertext())


def test_many_long_reasons_expand_layout_without_overlapping_included_box(
    prisma_inputs: PrismaInputs,
) -> None:
    exclusions = tuple(
        ExclusionCount(
            reason=f"Detailed primary exclusion reason number {index} with explanatory wording",
            count=1,
        )
        for index in range(1, 21)
    )
    inputs = replace(prisma_inputs, full_text_exclusions=exclusions, full_text_included=20)
    root = parse_svg(render_svg(counts(inputs)))

    groups = root.findall(f"{{{SVG_NS}}}g")
    reports_box_bottom = 0
    included_box_y = 0
    for group in groups:
        text = " ".join(group.itertext())
        rectangle = group.find(f"{{{SVG_NS}}}rect")
        if rectangle is None:
            continue
        y = int(rectangle.attrib["y"])
        height = int(rectangle.attrib["height"])
        if "Reports excluded" in text:
            reports_box_bottom = y + height
        if "Studies included in review" in text:
            included_box_y = y

    assert reports_box_bottom > 0
    assert included_box_y > reports_box_bottom


def test_unbroken_wide_labels_are_wrapped_to_box_capacity(prisma_inputs: PrismaInputs) -> None:
    inputs = replace(
        prisma_inputs,
        database_sources=(SourceCount(name="W" * 80, count=240),),
        full_text_exclusions=(ExclusionCount(reason="W" * 80, count=35),),
    )
    root = parse_svg(render_svg(counts(inputs)))

    for group in root.findall(f"{{{SVG_NS}}}g"):
        rectangle = group.find(f"{{{SVG_NS}}}rect")
        if rectangle is None:
            continue
        width = int(rectangle.attrib["width"])
        capacity = (width - 48) // 17
        for text in group.findall(f"{{{SVG_NS}}}text"):
            assert text.text is not None
            assert len(text.text) <= capacity
