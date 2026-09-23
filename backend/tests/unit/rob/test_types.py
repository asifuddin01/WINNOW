"""Public RoB value objects reject malformed runtime data when used outside typed code."""

import uuid
from dataclasses import replace
from typing import cast

import pytest

from app.rob import (
    Choice,
    DomainAssessment,
    DomainSummary,
    JudgementAxis,
    JudgementCount,
    SignallingQuestion,
    TemplateVariant,
    ToolTemplate,
    get_template,
    summary,
)


def test_choice_keys_and_labels_require_plain_strings() -> None:
    with pytest.raises(TypeError, match="key must be a string"):
        Choice(key=cast("str", 1), label="Low risk")
    with pytest.raises(TypeError, match="label must be a string"):
        Choice(key="low", label=cast("str", 1))


def test_question_answer_collection_must_be_an_immutable_tuple() -> None:
    answers = cast("tuple[str, ...]", ["yes", "no"])
    with pytest.raises(TypeError, match="must be a tuple"):
        SignallingQuestion(key="question", prompt="Prompt?", allowed_answers=answers)


def test_nested_template_collections_reject_wrong_item_types() -> None:
    invalid = cast("tuple[Choice, ...]", ("low",))
    with pytest.raises(TypeError, match="invalid value"):
        JudgementAxis(key="risk", name="Risk", allowed_judgements=invalid)


def test_domain_assessment_requires_a_uuid() -> None:
    with pytest.raises(TypeError, match="record_id must be a UUID"):
        DomainAssessment(
            record_id=cast("uuid.UUID", "record"),
            tool_key="rob2",
            variant_key="parallel_assignment",
            domain_key="randomisation_process",
            axis_key="risk_of_bias",
            judgement="low",
        )


@pytest.mark.parametrize(
    ("count", "error", "message"),
    [
        (cast("int", "1"), TypeError, "must be an integer"),
        (-1, ValueError, "must not be negative"),
    ],
)
def test_judgement_counts_validate_runtime_counts(
    count: int, error: type[Exception], message: str
) -> None:
    with pytest.raises(error, match=message):
        JudgementCount(judgement="low", label="Low risk", count=count)


def _valid_summary_row() -> DomainSummary:
    assessment = DomainAssessment(
        record_id=uuid.UUID(int=100),
        tool_key="rob2",
        variant_key="parallel_assignment",
        domain_key="randomisation_process",
        axis_key="risk_of_bias",
        judgement="low",
    )
    rows = (
        assessment,
        *(
            DomainAssessment(
                record_id=assessment.record_id,
                tool_key="rob2",
                variant_key="parallel_assignment",
                domain_key=domain.key,
                axis_key=domain.judgement_axes[0].key,
                judgement=domain.judgement_axes[0].allowed_judgements[0].key,
            )
            for domain in get_template("rob2").variants[0].domains[1:]
        ),
    )
    return summary(rows)[0]


@pytest.mark.parametrize(
    ("total", "error", "message"),
    [
        (cast("int", "1"), TypeError, "must be an integer"),
        (-1, ValueError, "must not be negative"),
        (2, ValueError, "must equal"),
    ],
)
def test_domain_summary_validates_total(total: int, error: type[Exception], message: str) -> None:
    with pytest.raises(error, match=message):
        replace(_valid_summary_row(), total=total)


def test_domain_summary_rejects_duplicate_judgement_counts() -> None:
    row = _valid_summary_row()
    duplicate = (row.counts[0], row.counts[0])
    with pytest.raises(ValueError, match="duplicate judgement"):
        replace(row, counts=duplicate, total=2)


def test_tool_url_validation_applies_to_direct_construction() -> None:
    template = get_template("rob2")
    with pytest.raises(TypeError, match="source_url must be a string"):
        replace(template, source_url=cast("str", 42))
    with pytest.raises(TypeError, match="variants must be a tuple"):
        replace(
            template,
            variants=cast("tuple[TemplateVariant, ...]", list(template.variants)),
        )


def test_summary_metadata_requires_nonblank_text() -> None:
    row = _valid_summary_row()
    with pytest.raises(ValueError, match="must not be blank"):
        replace(row, tool_name=" ")


def test_public_types_remain_frozen_templates() -> None:
    assert isinstance(get_template("rob2"), ToolTemplate)
