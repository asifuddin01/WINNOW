"""Every format, against exports from the databases guide 15 names.

The fixtures in tests/fixtures/parsers are shaped like the real thing: wrapped lines,
BOMs, Windows line endings, HTML entities, non-ASCII names, missing abstracts and a file
that stops mid-record.
"""

from pathlib import Path

import pytest

from app.parsers import ParsedRecord, ParseProblem, detect, parse
from app.parsers.common import normalise_author, normalise_doi, normalise_title, normalise_year
from app.parsers.xml_reader import MalformedXMLError

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "parsers"


def read(name: str) -> str:
    return FIXTURES.joinpath(name).read_bytes().decode("utf-8-sig")


def records(name: str, file_format: str) -> list[ParsedRecord]:
    return [r for r in parse(file_format, read(name)) if isinstance(r, ParsedRecord)]


def problems(name: str, file_format: str) -> list[ParseProblem]:
    return [p for p in parse(file_format, read(name)) if isinstance(p, ParseProblem)]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("ovid_embase.ris", "ris"),
        ("wos.ris", "ris"),
        ("cinahl.ris", "ris"),
        ("cochrane.ris", "ris"),
        ("messy.ris", "ris"),
        ("pubmed.nbib", "nbib"),
        ("pubmed.xml", "pubmed_xml"),
        ("endnote.xml", "endnote_xml"),
        ("zotero.bib", "bib"),
        ("zotero.rdf", "zotero_rdf"),
        ("scopus.csv", "csv"),
    ],
)
def test_the_format_is_recognised_from_the_file(name: str, expected: str) -> None:
    assert detect(name, read(name)) == expected
    # The extension is only a claim; the content decides (guide 12.4).
    assert detect("export.txt", read(name)) == (expected if expected != "csv" else None)


def test_ovid_embase_export() -> None:
    first, second = records("ovid_embase.ris", "ris")
    assert first.title == (
        "Rotating night shifts and sleep quality among hospital nurses: a prospective cohort study"
    )
    assert first.authors == ["Smith, J A", "Chowdhury, S"]
    assert first.year == 2019
    assert first.journal == "Journal of Advanced Nursing"
    assert first.pages == "812-824"
    assert first.doi == "10.1111/jan.13894"
    assert first.pmid == "31234567"  # Ovid puts it in AN when the database is MEDLINE
    # A MeSH heading keeps its own comma.
    assert "Sleep Initiation and Maintenance Disorders, epidemiology" in first.keywords
    assert first.abstract is not None
    assert first.abstract.startswith("AIM: To examine")
    assert second.title == "Shift work and fatigue: conference abstract"


def test_pubmed_medline_export() -> None:
    (record,) = records("pubmed.nbib", "nbib")
    assert record.pmid == "31234567"
    assert record.doi == "10.1111/jan.13894"
    assert record.authors == ["Smith, Jane A", "Chowdhury, Sara"]
    assert record.journal == "Journal of advanced nursing"
    assert record.year == 2019
    assert record.pages == "812-824"
    assert record.pmcid == "PMC6612345"
    assert record.publication_type == ["Journal Article", "Multicenter Study"]
    assert "shift work" in record.keywords


def test_pubmed_xml_export() -> None:
    first, second = records("pubmed.xml", "pubmed_xml")
    assert first.pmid == "31234567"
    assert first.doi == "10.1111/jan.13894"
    assert first.pmcid == "PMC6612345"
    assert first.journal == "Journal of advanced nursing"
    assert first.volume == "75"
    assert first.authors == ["Smith, Jane A", "Chowdhury, Sara"]
    assert first.abstract is not None
    assert "AIM: To examine" in first.abstract
    assert "METHODS: We followed" in first.abstract
    assert "\u2019" in first.abstract  # the numeric entity became a real apostrophe
    assert "Humans" in first.keywords
    # A record with only a MedlineDate still gets its year.
    assert second.year == 2020
    assert second.title == "Napping strategies for night shift workers."


def test_endnote_export() -> None:
    (record,) = records("endnote.xml", "endnote_xml")
    assert record.title == "Rotating night shifts and sleep quality among hospital nurses"
    assert record.authors == ["Smith, Jane A.", "Chowdhury, Sara"]
    assert record.journal == "Journal of Advanced Nursing"
    assert record.doi == "10.1111/jan.13894"
    assert record.pmid == "31234567"
    assert record.keywords == ["nurses", "shift work"]
    assert record.url is not None
    assert record.publication_type == ["Journal Article"]


def test_zotero_bibtex_export() -> None:
    first, second = records("zotero.bib", "bib")
    assert first.title.startswith("Rotating night shifts")  # type: ignore[union-attr]
    assert first.authors == ["Smith, Jane A.", "Chowdhury, Sara", "Müller, Jürgen"]
    assert first.doi == "10.1111/jan.13894"
    assert first.pages == "812-820"[:3] + "-824"  # "812--824" becomes an en dash range
    assert first.keywords == ["nurses", "shift work", "sleep quality"]
    assert second.title == "Napping strategies for night shift workers"
    assert second.publication_type == ["incollection"]


def test_zotero_rdf_export() -> None:
    article, chapter, preprint = records("zotero.rdf", "zotero_rdf")
    assert article.title == (
        "Rotating night shifts and sleep quality among hospital nurses: a cross-sectional study"
    )
    assert article.authors == ["Smith, Jane A.", "Chowdhury, Sara", "Müller, Jürgen"]
    # Zotero writes the journal, its volume and issue, and the DOI on the nested journal.
    assert article.journal == "Journal of Advanced Nursing"
    assert (article.volume, article.issue, article.pages) == ("75", "4", "812-824")
    assert article.doi == "10.1111/jan.13894"
    # PubMed ids live in "Extra".
    assert (article.pmid, article.pmcid) == ("31234567", "PMC6543210")
    assert article.year == 2019
    assert article.abstract is not None
    assert article.abstract.startswith("Aims: To assess sleep quality")
    assert "\n\nDesign:" in article.abstract
    assert article.keywords == ["Humans", "nurses", "shift work"]
    assert article.language == "eng"
    assert article.url == "https://onlinelibrary.wiley.com/doi/10.1111/jan.13894"
    assert article.publication_type == ["Journal article"]

    # The book is a separate node, after the chapter that points at it; editors are not
    # authors.
    assert chapter.title == "Napping strategies for night shift workers"
    assert chapter.authors == ["World Health Organization"]
    assert chapter.journal == "Sleep and Shift Work in Healthcare"
    assert chapter.isbn == "978-0-19-883551-9"
    assert chapter.publication_type == ["Book section"]

    # A DOI kept in "Extra", and a PubMed id read from a PubMed link.
    assert preprint.doi == "10.1101/2020.01.01.123456"
    assert preprint.pmid == "32000000"
    assert preprint.journal is None


def test_zotero_rdf_skips_attachments_notes_and_collections() -> None:
    (problem,) = problems("zotero.rdf", "zotero_rdf")
    # The fourth reference, counting only references.
    assert (problem.where(), problem.reason) == ("record 4", "no title, DOI or PubMed id")


def test_zotero_rdf_without_pointers_reads_in_one_pass() -> None:
    text = read("zotero.rdf").replace(
        '<dcterms:isPartOf rdf:resource="urn:isbn:978-0-19-883551-9"/>', ""
    )
    titles = [r.title for r in parse("zotero_rdf", text) if isinstance(r, ParsedRecord)]
    assert titles[1] == "Napping strategies for night shift workers"


def test_a_zotero_rdf_file_that_breaks_off_is_reported() -> None:
    with pytest.raises(MalformedXMLError):
        list(parse("zotero_rdf", read("zotero.rdf")[:3000]))


def test_scopus_csv_export() -> None:
    first, second = records("scopus.csv", "csv")
    assert first.authors == ["Smith, J.A.", "Chowdhury, S."]
    assert first.pages == "812-824"  # Scopus splits the range over two columns
    assert first.doi == "10.1111/jan.13894"
    assert first.keywords[:2] == ["nurses", "shift work"]
    assert first.url is not None
    assert second.publication_type == ["Review"]


def test_web_of_science_and_cinahl_and_cochrane() -> None:
    (wos,) = records("wos.ris", "ris")
    assert wos.journal == "JOURNAL OF ADVANCED NURSING"
    assert wos.doi == "10.1111/jan.13894"
    assert wos.keywords == ["nurses", "shift work", "sleep quality"]

    (cinahl,) = records("cinahl.ris", "ris")
    assert cinahl.title == "Rotating night shifts and sleep quality among hospital nurses."
    assert cinahl.year == 2019
    assert cinahl.abstract is not None

    (cochrane,) = records("cochrane.ris", "ris")
    assert cochrane.doi == "10.1002/14651858.cd012345.pub2"
    assert cochrane.journal == "Cochrane Database of Systematic Reviews"


def test_a_messy_file_still_reads(tmp_path: Path) -> None:
    """A BOM, Windows line endings, an entity, accents, and no ER on the last record."""
    parsed = list(parse("ris", read("messy.ris")))
    kept = [item for item in parsed if isinstance(item, ParsedRecord)]
    refused = [item for item in parsed if isinstance(item, ParseProblem)]
    assert [record.title for record in kept] == [
        "Café workers & sleep: a pilot study with a wrapped title",
        "Last record with no ER line",
    ]
    assert kept[0].authors == ["Müller, Jürgen"]
    assert kept[0].year == 2018
    assert kept[0].doi == "10.1000/abc.123"  # the resolver prefix and full stop are gone
    assert [problem.reason for problem in refused] == ["no title, DOI or PubMed id"]
    assert refused[0].unit == "line"
    assert tmp_path.exists()


def test_a_record_without_a_title_or_id_is_reported_not_dropped_silently() -> None:
    assert [p.reason for p in problems("messy.ris", "ris")] == ["no title, DOI or PubMed id"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://doi.org/10.1136/BMJ.L1234", "10.1136/bmj.l1234"),
        ("doi: 10.1000/xyz123.", "10.1000/xyz123"),
        ("info:doi/10.1000/abc", "10.1000/abc"),
        ("not a doi", None),
        (None, None),
    ],
)
def test_doi_normalisation(raw: str | None, expected: str | None) -> None:
    assert normalise_doi(raw) == expected


def test_title_normalisation_folds_accents_and_punctuation() -> None:
    assert normalise_title("Café  workers & sleep: a <i>pilot</i> study!") == (
        "cafe workers sleep a pilot study"
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("2019 Jul 3", 2019), ("c2020", 2020), ("2018-2019", 2018), ("no year", None), (1999, 1999)],
)
def test_year_normalisation(raw: str | int, expected: int | None) -> None:
    assert normalise_year(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Smith JA", "Smith, JA"),
        ("Smith J.A.", "Smith, J.A."),
        ("John Smith", "Smith, John"),
        ("Smith, Jane A", "Smith, Jane A"),
        # Four words or more is taken to be a body, not a person.
        (
            "World Health Organization Collaborating Centre",
            "World Health Organization Collaborating Centre",
        ),
    ],
)
def test_author_normalisation(raw: str, expected: str) -> None:
    assert normalise_author(raw) == expected


def test_xml_entities_pointing_at_the_server_are_refused() -> None:
    """Guide 12.10: an XXE payload in an XML import is harmless."""
    from app.parsers.endnote_xml import parse as parse_endnote

    payload = (
        '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        "<records><record><titles><title>&x;</title></titles></record></records>"
    )
    with pytest.raises(Exception, match="Entit"):
        list(parse_endnote(payload))
    with pytest.raises(Exception, match="Entit"):
        list(parse("zotero_rdf", payload.replace("<records>", "<rdf:RDF>")))
