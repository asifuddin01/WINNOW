"""The awkward corners of each reader: fallbacks, caps, and files that stop early."""

import pytest

from app.parsers import csv_parser, detect, parse
from app.parsers.common import MAX_LIST, ParsedRecord, ParseProblem, clean_abstract, terms_from
from app.parsers.nbib import parse as parse_nbib
from app.parsers.ris import parse as parse_ris
from app.services.search import parse_query


def only_records(items: object) -> list[ParsedRecord]:
    return [item for item in items if isinstance(item, ParsedRecord)]  # type: ignore[union-attr]


# --- MEDLINE -----------------------------------------------------------------------------


def test_medline_falls_back_to_short_author_and_abbreviated_journal() -> None:
    (record,) = only_records(
        parse_nbib("PMID- 1\nTI  - A title\nAU  - Smith JA\nTA  - J Adv Nurs\n")
    )
    assert record.authors == ["Smith, JA"]
    assert record.journal == "J Adv Nurs"


def test_medline_reads_the_doi_from_aid_when_lid_has_none() -> None:
    (record,) = only_records(
        parse_nbib(
            "PMID- 1\nTI  - A title\nLID - S0140-6736(20)30183-5 [pii]\n"
            "AID - 10.1016/S0140-6736(20)30183-5 [doi]\n"
        )
    )
    assert record.doi == "10.1016/s0140-6736(20)30183-5"


def test_medline_without_a_pmid_still_needs_a_title() -> None:
    problems = [p for p in parse_nbib("OWN - NLM\nLA  - eng\n") if isinstance(p, ParseProblem)]
    assert [problem.reason for problem in problems] == ["no title, DOI or PubMed id"]


# --- RIS ---------------------------------------------------------------------------------


def test_ris_pages_with_only_a_start_page() -> None:
    (record,) = only_records(parse_ris("TY  - JOUR\nTI  - T\nSP  - 112\nER  - \n"))
    assert record.pages == "112"


def test_ris_starts_a_new_record_when_a_file_forgets_its_end_markers() -> None:
    text = "TY  - JOUR\nTI  - First\nTY  - JOUR\nTI  - Second\n"
    assert [record.title for record in only_records(parse_ris(text))] == ["First", "Second"]


def test_ris_caps_a_runaway_repeated_tag() -> None:
    text = "TY  - JOUR\nTI  - T\n" + "".join(f"KW  - term{n}\n" for n in range(MAX_LIST + 50))
    (record,) = only_records(parse_ris(text + "ER  - \n"))
    assert len(record.keywords) == MAX_LIST


# --- CSV ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "delimiter"),
    [
        ("Title,DOI\na,b\n", ","),
        ("Title;DOI\na;b\n", ";"),
        ("Title\tDOI\na\tb\n", "\t"),
    ],
)
def test_csv_sniffs_the_delimiter(text: str, delimiter: str) -> None:
    assert csv_parser.delimiter_of(text) == delimiter
    assert csv_parser.columns_of(text) == ["Title", "DOI"]


def test_csv_without_a_usable_column_says_so_once() -> None:
    problems = list(parse("csv", "Notes,Comments\nsomething,else\n"))
    assert len(problems) == 1
    assert isinstance(problems[0], ParseProblem)
    assert "title" in problems[0].reason


def test_csv_rows_can_be_sampled_for_the_mapping_step() -> None:
    rows = csv_parser.sample_rows("Title,Year\nA,2019\nB,2020\nC,2021\n", limit=2)
    assert rows == [{"Title": "A", "Year": "2019"}, {"Title": "B", "Year": "2020"}]


def test_csv_mapping_is_only_a_suggestion() -> None:
    columns = ["Article Title", "Publication Year", "Nickname"]
    assert csv_parser.suggest_mapping(columns) == {
        "Article Title": "title",
        "Publication Year": "year",
    }


# --- Shared ------------------------------------------------------------------------------


def test_an_empty_or_unreadable_file_has_no_format() -> None:
    assert detect("notes.txt", "just some prose about nurses") is None
    assert detect("empty.txt", "") is None


def test_abstract_paragraphs_survive_but_tags_do_not() -> None:
    cleaned = clean_abstract("<p>First part.</p><p>Second part &amp; more.</p>")
    assert cleaned == "First part.\n\nSecond part & more."


def test_terms_keep_commas_unless_the_format_uses_them_as_separators() -> None:
    assert terms_from(["Neoplasms, Second Primary; Humans"]) == [
        "Neoplasms, Second Primary",
        "Humans",
    ]
    assert terms_from(["nurses, shift work"], commas=True) == ["nurses", "shift work"]


# --- Search syntax ------------------------------------------------------------------------


def test_search_ignores_an_unknown_field_but_keeps_the_words() -> None:
    query = parse_query("colour:blue sleep")
    assert query.text == "colour:blue sleep"
    assert query.is_empty() is False


def test_an_empty_search_is_empty() -> None:
    assert parse_query("").is_empty()
    assert parse_query("   ").is_empty()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("year:2020..", (2020, None)),
        ("year:..2020", (None, 2020)),
        ("year:2020", (2020, 2020)),
        ("year:nonsense", (None, None)),
    ],
)
def test_year_ranges(raw: str, expected: tuple[int | None, int | None]) -> None:
    query = parse_query(raw)
    assert (query.year_from, query.year_to) == expected


def test_a_quoted_field_value_keeps_its_spaces() -> None:
    query = parse_query('journal:"Sleep Health" author:"van der Berg"')
    assert query.journals == ["Sleep Health"]
    assert query.authors == ["van der Berg"]
