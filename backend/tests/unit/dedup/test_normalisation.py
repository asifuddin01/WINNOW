"""Title normalisation matches the import-time database representation."""

import pytest

from app.dedup import normalise_title


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        (
            "Café-au-lait spots in neurofibromatosis: a cohort study.",
            "cafe au lait spots in neurofibromatosis a cohort study",
        ),
        ("  Multiple\tspaces\nand lines  ", "multiple spaces and lines"),
        ("<i>Über</i>—therapy &amp; outcomes", "uber therapy outcomes"),
        ("“L'étude”: déjà-vu!", "l etude deja vu"),
        ("", ""),
    ],
)
def test_normalise_title(title: str, expected: str) -> None:
    assert normalise_title(title) == expected


def test_punctuation_becomes_space_instead_of_joining_words() -> None:
    assert normalise_title("meta-analysis/co-design") == "meta analysis co design"


def test_scientific_comparisons_are_not_mistaken_for_html_tags() -> None:
    title = "LDL < 70 mg/dL compared with > 70 mg/dL"
    assert normalise_title(title) == "ldl < 70 mg dl compared with > 70 mg dl"
