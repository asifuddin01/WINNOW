"""Frozen value objects for pure PRISMA count calculations and rendering."""

from dataclasses import dataclass
from unicodedata import normalize


def _validate_count(field_name: str, value: object) -> None:
    if type(value) is not int:
        msg = f"{field_name} must be an integer"
        raise TypeError(msg)
    if value < 0:
        msg = f"{field_name} must not be negative"
        raise ValueError(msg)


def _validate_xml_text(field_name: str, value: object) -> None:
    if type(value) is not str:
        msg = f"{field_name} must be a string"
        raise TypeError(msg)
    if not value.strip():
        msg = f"{field_name} must not be blank"
        raise ValueError(msg)
    for character in value:
        codepoint = ord(character)
        if (
            codepoint in {0x09, 0x0A, 0x0D}
            or 0x20 <= codepoint <= 0xD7FF
            or 0xE000 <= codepoint <= 0xFFFD
            or 0x10000 <= codepoint <= 0x10FFFF
        ):
            continue
        msg = f"{field_name} contains a character that XML 1.0 cannot represent"
        raise ValueError(msg)


def _normalised_label(value: str) -> str:
    return normalize("NFKC", value).strip().casefold()


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceCount:
    """A grouped database, register or manual source and its identified-record count."""

    name: str
    count: int

    def __post_init__(self) -> None:
        _validate_xml_text("name", self.name)
        _validate_count("count", self.count)


@dataclass(frozen=True, slots=True, kw_only=True)
class ExclusionCount:
    """A mutually exclusive primary full-text exclusion reason and report count."""

    reason: str
    count: int

    def __post_init__(self) -> None:
        _validate_xml_text("reason", self.reason)
        _validate_count("count", self.count)


def _validate_sources(field_name: str, values: tuple[SourceCount, ...]) -> None:
    if not isinstance(values, tuple):
        msg = f"{field_name} must be a tuple"
        raise TypeError(msg)
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, SourceCount):
            msg = f"{field_name} must contain SourceCount values"
            raise TypeError(msg)
        key = _normalised_label(value.name)
        if key in seen:
            msg = f"{field_name} contains a duplicate source name"
            raise ValueError(msg)
        seen.add(key)


def _validate_exclusions(field_name: str, values: tuple[ExclusionCount, ...]) -> None:
    if not isinstance(values, tuple):
        msg = f"{field_name} must be a tuple"
        raise TypeError(msg)
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, ExclusionCount):
            msg = f"{field_name} must contain ExclusionCount values"
            raise TypeError(msg)
        key = _normalised_label(value.reason)
        if key in seen:
            msg = f"{field_name} contains a duplicate reason"
            raise ValueError(msg)
        seen.add(key)


@dataclass(frozen=True, slots=True, kw_only=True)
class PrismaInputs:
    """Database-derived and manual values needed to calculate a PRISMA flow."""

    database_sources: tuple[SourceCount, ...]
    other_sources: tuple[SourceCount, ...]
    duplicates_removed: int
    records_removed_other_reasons: int
    non_duplicate_records: int
    title_abstract_excluded: int
    title_abstract_included: int
    reports_not_retrieved: int
    full_text_exclusions: tuple[ExclusionCount, ...]
    full_text_included: int

    def __post_init__(self) -> None:
        _validate_sources("database_sources", self.database_sources)
        _validate_sources("other_sources", self.other_sources)
        _validate_exclusions("full_text_exclusions", self.full_text_exclusions)
        for field_name, value in (
            ("duplicates_removed", self.duplicates_removed),
            ("records_removed_other_reasons", self.records_removed_other_reasons),
            ("non_duplicate_records", self.non_duplicate_records),
            ("title_abstract_excluded", self.title_abstract_excluded),
            ("title_abstract_included", self.title_abstract_included),
            ("reports_not_retrieved", self.reports_not_retrieved),
            ("full_text_included", self.full_text_included),
        ):
            _validate_count(field_name, value)


@dataclass(frozen=True, slots=True, kw_only=True)
class PrismaCounts:
    """Calculated values and ordered breakdowns shown in a PRISMA flow diagram."""

    database_sources: tuple[SourceCount, ...]
    other_sources: tuple[SourceCount, ...]
    records_identified_from_databases: int
    records_identified_from_other_sources: int
    records_identified_total: int
    duplicates_removed: int
    records_removed_other_reasons: int
    records_screened: int
    records_excluded: int
    reports_sought: int
    reports_not_retrieved: int
    reports_assessed: int
    reports_excluded_with_reasons: tuple[ExclusionCount, ...]
    reports_excluded_total: int
    studies_included: int

    def __post_init__(self) -> None:
        _validate_sources("database_sources", self.database_sources)
        _validate_sources("other_sources", self.other_sources)
        _validate_exclusions("reports_excluded_with_reasons", self.reports_excluded_with_reasons)
        for field_name, value in (
            ("records_identified_from_databases", self.records_identified_from_databases),
            ("records_identified_from_other_sources", self.records_identified_from_other_sources),
            ("records_identified_total", self.records_identified_total),
            ("duplicates_removed", self.duplicates_removed),
            ("records_removed_other_reasons", self.records_removed_other_reasons),
            ("records_screened", self.records_screened),
            ("records_excluded", self.records_excluded),
            ("reports_sought", self.reports_sought),
            ("reports_not_retrieved", self.reports_not_retrieved),
            ("reports_assessed", self.reports_assessed),
            ("reports_excluded_total", self.reports_excluded_total),
            ("studies_included", self.studies_included),
        ):
            _validate_count(field_name, value)

        database_total = sum(source.count for source in self.database_sources)
        other_total = sum(source.count for source in self.other_sources)
        exclusion_total = sum(item.count for item in self.reports_excluded_with_reasons)
        if self.records_identified_from_databases != database_total:
            raise ValueError("database source total does not match its breakdown")
        if self.records_identified_from_other_sources != other_total:
            raise ValueError("other-source total does not match its breakdown")
        if self.records_identified_total != database_total + other_total:
            raise ValueError("identified total does not match its source totals")
        removed_before_screening = self.duplicates_removed + self.records_removed_other_reasons
        if removed_before_screening > self.records_identified_total:
            raise ValueError("records removed before screening exceed records identified")
        if self.records_screened > self.records_identified_total - self.duplicates_removed:
            raise ValueError("records screened exceed records remaining after duplicate removal")
        if self.records_excluded + self.reports_sought > self.records_screened:
            raise ValueError("title/abstract outcomes exceed records screened")
        if self.reports_not_retrieved > self.reports_sought:
            raise ValueError("reports not retrieved exceed reports sought")
        if self.reports_assessed != self.reports_sought - self.reports_not_retrieved:
            raise ValueError("reports assessed must equal sought minus not retrieved")
        if self.reports_excluded_total != exclusion_total:
            raise ValueError("excluded total does not match its reason breakdown")
        if self.reports_excluded_total + self.studies_included > self.reports_assessed:
            raise ValueError("full-text outcomes exceed reports assessed")
