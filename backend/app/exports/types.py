"""One record as the citation writers read it."""

import re
from dataclasses import dataclass

_BREAKS = re.compile(r"[\r\n\t\x0b\x0c]+")
_CONTROL = re.compile(r"[\x00-\x08\x0e-\x1f\x7f]")

STAGES = (("ta", "Title/abstract"), ("ft", "Full text"))
EN_DASH, EM_DASH = "\u2013", "\u2014"


@dataclass(frozen=True, slots=True)
class ExportRecord:
    """A record and what the review decided about it.

    Statuses are the words Winnow stores: a final status (`included`, `not_retrievable`,
    …), or, for a reader blind to others' work, their own decision (`include`, …), in
    which case `mine` is true and the files say so.
    """

    id: str
    title: str | None = None
    abstract: str | None = None
    authors: tuple[str, ...] = ()
    year: int | None = None
    journal: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    url: str | None = None
    keywords: tuple[str, ...] = ()
    publication_type: tuple[str, ...] = ()
    language: str | None = None
    database: str | None = None
    ta_status: str | None = None
    ft_status: str | None = None
    ta_reasons: tuple[str, ...] = ()
    ft_reasons: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    mine: bool = False


def one_line(value: object) -> str:
    """A value on one line, without control characters: both formats are line based."""
    if value is None:
        return ""
    return _CONTROL.sub("", _BREAKS.sub(" ", str(value))).strip()


def decision_notes(record: ExportRecord) -> list[str]:
    """ "Title/abstract: excluded (Wrong population)" and the like, then labels and the id."""
    notes = []
    for key, stage in STAGES:
        status = getattr(record, f"{key}_status")
        # A record excluded at title and abstract never reaches full text; saying so on
        # every one of them is noise (the status field still carries it).
        if not status or status == "not_eligible":
            continue
        reasons = getattr(record, f"{key}_reasons")
        heading = f"My {stage.lower()} decision" if record.mine else stage
        words = status.replace("_", " ")
        notes.append(f"{heading}: {words}" + (f" ({'; '.join(reasons)})" if reasons else ""))
    if record.labels:
        notes.append(("My labels" if record.mine else "Labels") + ": " + "; ".join(record.labels))
    notes.append(f"Winnow ID: {record.id}")
    return [one_line(note) for note in notes]


def split_pages(pages: str | None) -> tuple[str, str]:
    """ "12-19" → ("12", "19"); "e123" → ("e123", "")."""
    text = one_line(pages)
    for dash in ("--", EN_DASH, EM_DASH, "-"):
        if dash in text:
            start, _, end = text.partition(dash)
            return start.strip(), end.strip()
    return text, ""
