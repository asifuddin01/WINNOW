"""The methods text (guide 8.15): how the review was screened, in words, with its numbers.

`methods_text` turns facts into two paragraphs, one for searching and title/abstract
screening, one for full texts and what followed. Every fact is optional and a missing one
drops its sentence: the text never states what the review does not hold. Numbers carry
thousands separators, kappa two decimals; spelling is British.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

NUMBER_WORDS = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")


@dataclass(frozen=True, slots=True)
class DatabaseSearch:
    name: str
    records: int
    searched_on: date | None = None


@dataclass(frozen=True, slots=True)
class Count:
    """A named number: another source's records, or an exclusion reason's reports."""

    name: str
    count: int


@dataclass(frozen=True, slots=True)
class Agreement:
    """Agreement at one stage. `kappa` is Cohen's for a single pair of reviewers or
    Fleiss' (`fleiss`) for three or more; several pairs give `kappa_range` instead."""

    kappa: float | None = None
    band: str | None = None
    percent: float | None = None
    fleiss: bool = False
    kappa_range: tuple[float, float] | None = None
    pairs: int = 1


@dataclass(frozen=True, slots=True)
class Resolutions:
    """Disagreements at one stage and how they were settled."""

    total: int
    by_discussion: int = 0
    by_third_reviewer: int = 0


@dataclass(frozen=True, slots=True)
class AiUse:
    records: int
    models: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MethodsFacts:
    databases: tuple[DatabaseSearch, ...] = ()
    other_sources: tuple[Count, ...] = ()
    duplicates_removed: int | None = None
    records_screened: int | None = None
    reviewers_ta: int | None = None
    reviewers_ft: int | None = None
    blind: bool | None = None
    agreement_ta: Agreement | None = None
    agreement_ft: Agreement | None = None
    resolutions_ta: Resolutions | None = None
    resolutions_ft: Resolutions | None = None
    ranked: bool = False
    # When screening stopped before every record was seen: the rule, in words.
    stopping_rule: str | None = None
    ai: AiUse | None = None
    reports_sought: int | None = None
    reports_not_retrieved: int | None = None
    reports_assessed: int | None = None
    reports_excluded: tuple[Count, ...] = ()
    studies_included: int | None = None
    extraction: Literal["single", "duplicate"] | None = None
    rob_tools: tuple[str, ...] = ()
    rob_duplicate: bool | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)


def n(value: int) -> str:
    return f"{value:,}"


def count_of(value: int, one: str, many: str | None = None) -> str:
    """ "1 record", "1,204 records"."""
    return f"{n(value)} {one if value == 1 else (many or one + 's')}"


def people(value: int) -> str:
    """ "one reviewer", "two reviewers", "12 reviewers"."""
    word = NUMBER_WORDS[value] if 0 <= value < len(NUMBER_WORDS) else n(value)
    return f"{word} reviewer" + ("" if value == 1 else "s")


def listed(items: Sequence[str]) -> str:
    """ "a", "a and b", "a, b and c"."""
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def day(value: date) -> str:
    return f"{value.day} {value:%B %Y}"


def capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def _agreement(agreement: Agreement | None) -> str | None:
    """ "agreement was 94.2% (Cohen's κ = 0.81, almost perfect)"."""
    if agreement is None:
        return None
    parts = []
    if agreement.kappa_range is not None:
        low, high = agreement.kappa_range
        parts.append(
            f"Cohen's κ ranged from {low:.2f} to {high:.2f} across {n(agreement.pairs)} "
            "pairs of reviewers"
        )
    elif agreement.kappa is not None:
        name = "Fleiss' κ" if agreement.fleiss else "Cohen's κ"
        band = f", {agreement.band}" if agreement.band else ""
        parts.append(f"{name} = {agreement.kappa:.2f}{band}")
    if agreement.percent is not None:
        head = f"agreement was {agreement.percent * 100:.1f}%"
        return f"{head} ({parts[0]})" if parts else head
    return parts[0] if parts else None


def _resolutions(resolutions: Resolutions | None, stage: str) -> str | None:
    if resolutions is None or resolutions.total == 0:
        return None
    how = []
    if resolutions.by_discussion:
        how.append(f"by discussion ({n(resolutions.by_discussion)})")
    if resolutions.by_third_reviewer:
        how.append(f"by a third reviewer ({n(resolutions.by_third_reviewer)})")
    settled = f" were resolved {' or '.join(how)}" if how else " were resolved"
    return f"Disagreements at {stage} ({n(resolutions.total)}){settled}."


def _screening(reviewers: int | None, blind: bool | None, what: str, records: int) -> str:
    subject = capital(people(reviewers)) if reviewers else "Reviewers"
    how = " independently" if reviewers and reviewers > 1 else ""
    screened = f"{subject}{how} screened {what} {count_of(records, 'record')}"
    if reviewers and reviewers > 1 and blind is not None:
        screened += (
            ", blinded to each other's decisions" if blind else ", seeing each other's decisions"
        )
    return screened


def _identification(facts: MethodsFacts) -> str | None:
    sources = [
        f"{database.name} ({count_of(database.records, 'record')}"
        + (f", searched {day(database.searched_on)}" if database.searched_on else "")
        + ")"
        for database in facts.databases
    ]
    others = [
        f"{source.name} ({count_of(source.count, 'record')})" for source in facts.other_sources
    ]
    if not sources and not others:
        return None
    text = f"We searched {listed(sources)}" if sources else ""
    if others:
        found = f"identified further records through {listed(others)}"
        text = f"{text} and {found}" if text else f"We {found}"
    return text + "."


def _first_paragraph(facts: MethodsFacts) -> list[str]:
    sentences = []
    if identified := _identification(facts):
        sentences.append(identified)
    if facts.records_screened is not None:
        screened = _screening(
            facts.reviewers_ta, facts.blind, "the titles and abstracts of", facts.records_screened
        )
        if removed := facts.duplicates_removed:
            screened = (
                f"After {count_of(removed, 'duplicate')} {'was' if removed == 1 else 'were'} "
                "removed, " + screened[:1].lower() + screened[1:]
            )
        agreement = _agreement(facts.agreement_ta)
        sentences.append(f"{screened}; {agreement}." if agreement else f"{screened}.")
    if resolved := _resolutions(facts.resolutions_ta, "title and abstract"):
        sentences.append(resolved)
    if facts.ranked:
        sentences.append(
            "Records were screened in order of predicted relevance, updated as decisions "
            "were made (active learning)."
        )
    if facts.stopping_rule:
        sentences.append(
            f"Title and abstract screening stopped before every record was seen, when "
            f"{facts.stopping_rule}."
        )
    if facts.ai and facts.ai.records:
        model = f" ({listed(list(facts.ai.models))})" if facts.ai.models else ""
        sentences.append(
            f"An AI assistant{model} suggested decisions for "
            f"{count_of(facts.ai.records, 'record')}; every decision was made by a reviewer."
        )
    return sentences


def _second_paragraph(facts: MethodsFacts) -> list[str]:
    sentences = []
    if facts.reports_sought:
        sought = f"We sought {count_of(facts.reports_sought, 'full-text report')}"
        if facts.reports_not_retrieved:
            missing = facts.reports_not_retrieved
            sought += f", of which {n(missing)} could not be retrieved"
        sentences.append(sought + ".")
    if facts.reports_assessed:
        assessed = _screening(
            facts.reviewers_ft, facts.blind, "the full texts of", facts.reports_assessed
        ).replace(" screened the full texts of", " assessed the full texts of")
        agreement = _agreement(facts.agreement_ft)
        sentences.append(f"{assessed}; {agreement}." if agreement else f"{assessed}.")
    if facts.reports_excluded:
        total = sum(reason.count for reason in facts.reports_excluded)
        reasons = listed(
            [f"{reason.name.lower()} ({n(reason.count)})" for reason in facts.reports_excluded]
        )
        sentences.append(
            f"{capital(count_of(total, 'report'))} {'was' if total == 1 else 'were'} "
            f"excluded: {reasons}."
        )
    if resolved := _resolutions(facts.resolutions_ft, "full text"):
        sentences.append(resolved)
    if facts.studies_included is not None:
        included = count_of(facts.studies_included, "study", "studies")
        sentences.append(
            f"{capital(included)} {'was' if facts.studies_included == 1 else 'were'} "
            "included in the review."
        )
    if facts.extraction == "duplicate":
        sentences.append("Two reviewers extracted data independently and resolved differences.")
    elif facts.extraction == "single":
        sentences.append("One reviewer extracted the data.")
    if facts.rob_tools:
        tools = listed(list(facts.rob_tools))
        how = " independently by two reviewers" if facts.rob_duplicate else ""
        sentences.append(f"Risk of bias was assessed{how} with {tools}.")
    return sentences


def methods_text(facts: MethodsFacts) -> str:
    """An editable description of how the review was screened; empty when there is nothing
    to describe yet."""
    paragraphs = [
        " ".join(sentences)
        for sentences in (_first_paragraph(facts), _second_paragraph(facts), list(facts.notes))
        if sentences
    ]
    return "\n\n".join(paragraphs)
