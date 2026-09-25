"""RIS and BibTeX writers (guide 8.16): what Winnow writes, Winnow and reference managers
read back, with the review's decisions kept."""

from dataclasses import replace

from app.exports import BibtexWriter, ExportRecord, write_bibtex, write_ris
from app.exports.types import decision_notes, one_line, split_pages
from app.parsers import bibtex, ris
from app.parsers.common import ParsedRecord

STUDY = ExportRecord(
    id="0192f0c1-0000-7000-8000-000000000001",
    title="Night shifts & sleep: 50% of nurses_{rotating}",
    abstract="AIM: to examine sleep.\nMETHODS: a cohort of 1,204 nurses.",
    authors=("Okafor, Ngozi", "Lindqvist, Elin"),
    year=2016,
    journal="Sleep Medicine",
    volume="12",
    issue="3",
    pages="112-119",
    doi="10.1000/sleep.1",
    pmid="30000001",
    url="https://example.org/sleep",
    keywords=("night work", "sleep"),
    language="eng",
    database="Embase",
    ta_status="included",
    ft_status="excluded",
    ft_reasons=("Wrong population", "Wrong design"),
    labels=("Key paper",),
)


def only(items: list[object]) -> ParsedRecord:
    [item] = items
    assert isinstance(item, ParsedRecord), item
    return item


def test_ris_reads_back_through_winnows_own_reader() -> None:
    text = write_ris([STUDY])
    assert text.startswith("TY  - JOUR\r\n")
    assert "\n" not in text.replace("\r\n", "")  # CRLF only; no stray line breaks
    back = only(list(ris.parse(text)))
    assert back.title == STUDY.title
    assert back.authors == ["Okafor, Ngozi", "Lindqvist, Elin"]
    assert (back.year, back.journal, back.volume, back.issue) == (2016, "Sleep Medicine", "12", "3")
    assert back.pages == "112-119"
    assert back.doi == "10.1000/sleep.1"
    assert back.pmid == "30000001"
    assert back.url == "https://example.org/sleep"
    assert back.keywords == ["night work", "sleep"]
    assert back.abstract == "AIM: to examine sleep. METHODS: a cohort of 1,204 nurses."


def test_ris_carries_the_decisions_in_notes_and_custom_fields() -> None:
    lines = write_ris([STUDY]).split("\r\n")
    assert "N1  - Title/abstract: included" in lines
    assert "N1  - Full text: excluded (Wrong population; Wrong design)" in lines
    assert "N1  - Labels: Key paper" in lines
    assert f"N1  - Winnow ID: {STUDY.id}" in lines
    assert "C1  - included" in lines
    assert "C2  - excluded" in lines
    assert "C3  - Wrong population; Wrong design" in lines
    assert "C4  - Key paper" in lines
    assert lines.index("ER  - ") == len(lines) - 3  # then the blank line between records


def test_a_blinded_readers_file_says_the_decisions_are_their_own() -> None:
    mine = replace(STUDY, ta_status="include", ft_status="not_eligible", ft_reasons=(), mine=True)
    assert decision_notes(mine) == [
        "My title/abstract decision: include",
        "My labels: Key paper",
        f"Winnow ID: {STUDY.id}",
    ]


def test_missing_fields_are_left_out_and_a_record_without_a_journal_is_generic() -> None:
    bare = ExportRecord(id="x", title="A grey-literature report")
    text = write_ris([bare])
    assert text.startswith("TY  - GEN\r\n")
    for tag in ("JO", "AU", "C1"):
        assert f"{tag}  -" not in text
    assert only(list(ris.parse(text))).title == "A grey-literature report"
    assert write_bibtex([bare]).startswith("@misc{winnownd,\n")


def test_a_formula_looking_title_is_written_as_it_is() -> None:
    risky = replace(STUDY, title='=HYPERLINK("http://evil")')
    assert only(list(ris.parse(write_ris([risky])))).title == '=HYPERLINK("http://evil")'
    assert only(list(bibtex.parse(write_bibtex([risky])))).title == '=HYPERLINK("http://evil")'


def test_bibtex_reads_back_with_special_characters_intact() -> None:
    text = write_bibtex([STUDY])
    assert text.startswith("@article{okafor2016,\n")
    assert r"Night shifts \& sleep: 50\% of nurses\_\{rotating\}" in text
    assert "pages = {112--119}" in text
    back = only(list(bibtex.parse(text)))
    assert back.title == STUDY.title
    assert back.authors == ["Okafor, Ngozi", "Lindqvist, Elin"]
    assert (back.year, back.journal, back.volume, back.issue) == (2016, "Sleep Medicine", "12", "3")
    assert back.pages == "112-119"
    assert (back.doi, back.pmid) == ("10.1000/sleep.1", "30000001")
    assert back.keywords == ["night work", "sleep"]
    assert "note = {Title/abstract: included. Full text: excluded (Wrong population" in text


def test_bibtex_escapes_every_latex_special() -> None:
    odd = replace(STUDY, title=r"a\b ~ ^ $5 #1 {x}")
    text = write_bibtex([odd])
    assert r"a\textbackslash{}b \textasciitilde{} \textasciicircum{} \$5 \#1 \{x\}" in text
    assert only(list(bibtex.parse(text))).title == r"a\b ~ ^ $5 #1 {x}"


def test_citation_keys_are_ascii_and_unique_across_batches() -> None:
    writer = BibtexWriter()
    same = [replace(STUDY, authors=("Ødegård, Åse",)) for _ in range(3)]
    first = writer.write(same[:2])
    second = writer.write(same[2:])
    keys = [
        line.split("{")[1].rstrip(",")
        for line in (first + second).splitlines()
        if line.startswith("@")
    ]
    assert keys == ["degard2016", "degard2016a", "degard2016b"]
    written_first = BibtexWriter().write([replace(STUDY, authors=("Ngozi Okafor",), year=None)])
    assert written_first.startswith("@article{okafornd,")


def test_keys_keep_going_past_z() -> None:
    writer = BibtexWriter()
    keys = [writer._key(STUDY) for _ in range(30)]
    assert keys[:3] == ["okafor2016", "okafor2016a", "okafor2016b"]
    assert keys[27:] == ["okafor2016aa", "okafor2016ab", "okafor2016ac"]
    assert len(set(keys)) == 30


def test_pages_and_lines() -> None:
    assert split_pages("112-119") == ("112", "119")
    assert split_pages("112\u2013119") == ("112", "119")
    assert split_pages("e1234") == ("e1234", "")
    assert split_pages(None) == ("", "")
    assert one_line("a\r\nb\tc\x07d") == "a b cd"
    assert one_line(None) == ""
