"""Frozen value objects for risk-of-bias templates and summaries."""

import re
import unicodedata
import uuid
from dataclasses import dataclass
from typing import cast
from urllib.parse import urlsplit

_KEY_PATTERN = re.compile(r"[a-z][a-z0-9_]*\Z")


def _validate_key(field_name: str, value: object) -> None:
    if type(value) is not str:
        msg = f"{field_name} must be a string"
        raise TypeError(msg)
    if _KEY_PATTERN.fullmatch(value) is None:
        msg = f"{field_name} must be a lowercase snake-case key"
        raise ValueError(msg)


def _validate_text(field_name: str, value: object) -> None:
    if type(value) is not str:
        msg = f"{field_name} must be a string"
        raise TypeError(msg)
    if not value.strip():
        msg = f"{field_name} must not be blank"
        raise ValueError(msg)
    if any(unicodedata.category(character) in {"Cc", "Cs"} for character in value):
        msg = f"{field_name} must not contain control characters"
        raise ValueError(msg)


def _validate_url(field_name: str, value: object) -> None:
    _validate_text(field_name, value)
    parsed = urlsplit(cast("str", value))
    if parsed.scheme != "https" or not parsed.netloc or parsed.username is not None:
        msg = f"{field_name} must be an HTTPS URL without credentials"
        raise ValueError(msg)


def _validate_tuple(field_name: str, value: object, item_type: type[object]) -> tuple[object, ...]:
    if type(value) is not tuple:
        msg = f"{field_name} must be a tuple"
        raise TypeError(msg)
    if not value:
        msg = f"{field_name} must not be empty"
        raise ValueError(msg)
    if not all(type(item) is item_type for item in value):
        msg = f"{field_name} contains an invalid value"
        raise TypeError(msg)
    return value


def _normalised_label(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _validate_unique(
    field_name: str,
    values: tuple[object, ...],
    *,
    key: str,
) -> None:
    seen: set[str] = set()
    for value in values:
        candidate = cast("str", getattr(value, key))
        normalised = _normalised_label(candidate)
        if normalised in seen:
            msg = f"{field_name} contains a duplicate {key}"
            raise ValueError(msg)
        seen.add(normalised)


@dataclass(frozen=True, slots=True, kw_only=True)
class Choice:
    """One stable machine key and human-readable label offered by a template."""

    key: str
    label: str

    def __post_init__(self) -> None:
        _validate_key("key", self.key)
        _validate_text("label", self.label)


@dataclass(frozen=True, slots=True, kw_only=True)
class SignallingQuestion:
    """One concise guidance prompt and its ordered answer choices."""

    key: str
    prompt: str
    allowed_answers: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_key("key", self.key)
        _validate_text("prompt", self.prompt)
        if type(self.allowed_answers) is not tuple:
            msg = "allowed_answers must be a tuple"
            raise TypeError(msg)
        if not self.allowed_answers:
            msg = "allowed_answers must not be empty"
            raise ValueError(msg)
        seen: set[str] = set()
        for answer in self.allowed_answers:
            _validate_key("allowed_answers value", answer)
            if answer in seen:
                msg = "allowed_answers contains a duplicate value"
                raise ValueError(msg)
            seen.add(answer)


@dataclass(frozen=True, slots=True, kw_only=True)
class JudgementAxis:
    """A domain dimension and its ordered set of permitted final judgements."""

    key: str
    name: str
    allowed_judgements: tuple[Choice, ...]

    def __post_init__(self) -> None:
        _validate_key("key", self.key)
        _validate_text("name", self.name)
        values = _validate_tuple("allowed_judgements", self.allowed_judgements, Choice)
        _validate_unique("allowed_judgements", values, key="key")


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainTemplate:
    """One appraisal domain with guidance prompts and one or more judgement axes."""

    key: str
    name: str
    signalling_questions: tuple[SignallingQuestion, ...]
    judgement_axes: tuple[JudgementAxis, ...]

    def __post_init__(self) -> None:
        _validate_key("key", self.key)
        _validate_text("name", self.name)
        questions = _validate_tuple(
            "signalling_questions", self.signalling_questions, SignallingQuestion
        )
        axes = _validate_tuple("judgement_axes", self.judgement_axes, JudgementAxis)
        _validate_unique("signalling_questions", questions, key="key")
        _validate_unique("judgement_axes", axes, key="key")


@dataclass(frozen=True, slots=True, kw_only=True)
class TemplateVariant:
    """A study-design variant containing an ordered set of appraisal domains."""

    key: str
    name: str
    domains: tuple[DomainTemplate, ...]

    def __post_init__(self) -> None:
        _validate_key("key", self.key)
        _validate_text("name", self.name)
        values = _validate_tuple("domains", self.domains, DomainTemplate)
        _validate_unique("domains", values, key="key")


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolTemplate:
    """A versioned risk-of-bias instrument loaded from one validated JSON resource."""

    key: str
    name: str
    version: str
    source_url: str
    content_note: str
    variants: tuple[TemplateVariant, ...]

    def __post_init__(self) -> None:
        _validate_key("key", self.key)
        _validate_text("name", self.name)
        _validate_text("version", self.version)
        _validate_url("source_url", self.source_url)
        _validate_text("content_note", self.content_note)
        values = _validate_tuple("variants", self.variants, TemplateVariant)
        _validate_unique("variants", values, key="key")


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainAssessment:
    """One final judgement for a record, tool variant, domain and judgement axis."""

    record_id: uuid.UUID
    tool_key: str
    variant_key: str
    domain_key: str
    axis_key: str
    judgement: str

    def __post_init__(self) -> None:
        if type(self.record_id) is not uuid.UUID:
            msg = "record_id must be a UUID"
            raise TypeError(msg)
        for field_name, value in (
            ("tool_key", self.tool_key),
            ("variant_key", self.variant_key),
            ("domain_key", self.domain_key),
            ("axis_key", self.axis_key),
            ("judgement", self.judgement),
        ):
            _validate_key(field_name, value)


@dataclass(frozen=True, slots=True, kw_only=True)
class JudgementCount:
    """A permitted judgement, display label and observed count for one summary row."""

    judgement: str
    label: str
    count: int

    def __post_init__(self) -> None:
        _validate_key("judgement", self.judgement)
        _validate_text("label", self.label)
        if type(self.count) is not int:
            msg = "count must be an integer"
            raise TypeError(msg)
        if self.count < 0:
            msg = "count must not be negative"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainSummary:
    """Ordered traffic-light or score counts for one tool/domain judgement axis."""

    tool_key: str
    tool_name: str
    variant_key: str
    variant_name: str
    domain_key: str
    domain_name: str
    axis_key: str
    axis_name: str
    counts: tuple[JudgementCount, ...]
    total: int

    def __post_init__(self) -> None:
        for field_name, value in (
            ("tool_key", self.tool_key),
            ("variant_key", self.variant_key),
            ("domain_key", self.domain_key),
            ("axis_key", self.axis_key),
        ):
            _validate_key(field_name, value)
        for field_name, value in (
            ("tool_name", self.tool_name),
            ("variant_name", self.variant_name),
            ("domain_name", self.domain_name),
            ("axis_name", self.axis_name),
        ):
            _validate_text(field_name, value)
        values = _validate_tuple("counts", self.counts, JudgementCount)
        _validate_unique("counts", values, key="judgement")
        if type(self.total) is not int:
            msg = "total must be an integer"
            raise TypeError(msg)
        if self.total < 0:
            msg = "total must not be negative"
            raise ValueError(msg)
        if sum(item.count for item in self.counts) != self.total:
            msg = "total must equal the sum of judgement counts"
            raise ValueError(msg)
