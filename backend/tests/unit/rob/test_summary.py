"""Risk-of-bias summaries validate complete records and preserve template order."""

import json
import uuid
from dataclasses import replace
from typing import cast

import pytest

from app.rob import (
    BUILTIN_TEMPLATES,
    DomainAssessment,
    DomainSummary,
    ToolTemplate,
    get_template,
    load_template_json,
    summary,
)


def complete_assessment(
    tool_key: str,
    variant_key: str,
    record_id: uuid.UUID,
    *,
    use_last_judgement: bool = False,
) -> tuple[DomainAssessment, ...]:
    template = get_template(tool_key)
    variant = next(item for item in template.variants if item.key == variant_key)
    rows: list[DomainAssessment] = []
    for domain in variant.domains:
        for axis in domain.judgement_axes:
            judgement = (
                axis.allowed_judgements[-1].key
                if use_last_judgement
                else axis.allowed_judgements[0].key
            )
            rows.append(
                DomainAssessment(
                    record_id=record_id,
                    tool_key=tool_key,
                    variant_key=variant_key,
                    domain_key=domain.key,
                    axis_key=axis.key,
                    judgement=judgement,
                )
            )
    return tuple(rows)


def row_by_key(rows: tuple[DomainSummary, ...], domain: str, axis: str) -> DomainSummary:
    return next(row for row in rows if row.domain_key == domain and row.axis_key == axis)


def test_summary_counts_each_allowed_judgement_and_includes_zeroes() -> None:
    assessments = (
        *complete_assessment("rob2", "parallel_assignment", uuid.UUID(int=1)),
        *complete_assessment(
            "rob2", "parallel_assignment", uuid.UUID(int=2), use_last_judgement=True
        ),
    )

    result = summary(assessments)

    assert len(result) == 5
    assert tuple(row.domain_key for row in result) == tuple(
        domain.key for domain in get_template("rob2").variants[0].domains
    )
    first = result[0]
    assert first.total == 2
    assert tuple((item.judgement, item.count) for item in first.counts) == (
        ("low", 1),
        ("some_concerns", 0),
        ("high", 1),
    )


def test_summary_is_independent_of_assessment_input_order() -> None:
    assessments = (
        *complete_assessment("rob2", "parallel_assignment", uuid.UUID(int=1)),
        *complete_assessment(
            "rob2", "parallel_assignment", uuid.UUID(int=2), use_last_judgement=True
        ),
    )
    assert summary(assessments) == summary(tuple(reversed(assessments)))


def test_quadas2_emits_separate_risk_and_applicability_rows() -> None:
    result = summary(complete_assessment("quadas2", "diagnostic_accuracy", uuid.UUID(int=3)))

    assert len(result) == 7
    patient_risk = row_by_key(result, "patient_selection", "risk_of_bias")
    patient_applicability = row_by_key(result, "patient_selection", "applicability")
    assert patient_risk.counts[0].label == "Low risk"
    assert patient_applicability.counts[0].label == "Low concern"
    assert all(row.total == 1 for row in result)


def test_nos_keeps_ordinal_star_counts_without_inventing_cutoffs() -> None:
    result = summary(complete_assessment("nos", "cohort", uuid.UUID(int=4)))

    assert len(result) == 3
    selection = row_by_key(result, "selection", "stars")
    assert tuple(item.judgement for item in selection.counts) == (
        "stars_0",
        "stars_1",
        "stars_2",
        "stars_3",
        "stars_4",
    )
    assert tuple(item.count for item in selection.counts) == (1, 0, 0, 0, 0)


def test_multiple_tools_are_emitted_in_template_order() -> None:
    assessments = (
        *complete_assessment("quadas2", "diagnostic_accuracy", uuid.UUID(int=5)),
        *complete_assessment("rob2", "parallel_assignment", uuid.UUID(int=5)),
    )
    result = summary(tuple(reversed(assessments)))
    first_index = next(index for index, row in enumerate(result) if row.tool_key == "rob2")
    quadas_index = next(index for index, row in enumerate(result) if row.tool_key == "quadas2")
    assert first_index < quadas_index


def test_empty_assessment_collection_has_no_summary_rows() -> None:
    assert summary(()) == ()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"tool_key": "unknown"}, "unknown risk-of-bias tool"),
        ({"variant_key": "unknown"}, "unknown variant"),
        ({"domain_key": "unknown"}, "unknown domain axis"),
        ({"axis_key": "unknown"}, "unknown domain axis"),
        ({"judgement": "unknown"}, "invalid judgement"),
    ],
)
def test_unknown_template_coordinates_and_judgements_are_rejected(
    changes: dict[str, object], message: str
) -> None:
    row = complete_assessment("rob2", "parallel_assignment", uuid.UUID(int=6))[0]
    with pytest.raises(ValueError, match=message):
        summary((replace(row, **changes),))  # type: ignore[arg-type]


def test_duplicate_record_domain_axis_is_rejected() -> None:
    rows = complete_assessment("rob2", "parallel_assignment", uuid.UUID(int=7))
    with pytest.raises(ValueError, match="only one judgement"):
        summary((*rows, rows[0]))


def test_one_record_cannot_mix_nos_variants() -> None:
    record_id = uuid.UUID(int=8)
    cohort_row = complete_assessment("nos", "cohort", record_id)[0]
    case_control_row = complete_assessment("nos", "case_control", record_id)[0]
    with pytest.raises(ValueError, match="cannot mix"):
        summary((cohort_row, case_control_row))


def test_incomplete_record_is_rejected_with_missing_cells() -> None:
    row = complete_assessment("rob2", "parallel_assignment", uuid.UUID(int=9))[0]
    with pytest.raises(ValueError, match=r"incomplete; missing:.*risk_of_bias"):
        summary((row,))


def test_non_assessment_values_are_rejected() -> None:
    invalid = cast("tuple[DomainAssessment, ...]", ("not an assessment",))
    with pytest.raises(TypeError, match="DomainAssessment"):
        summary(invalid)


def test_duplicate_custom_template_keys_are_rejected() -> None:
    template = get_template("rob2")
    with pytest.raises(ValueError, match="duplicate tool key"):
        summary((), templates=(template, template))


def test_non_template_values_are_rejected() -> None:
    invalid = cast("tuple[ToolTemplate, ...]", ("not a template",))
    with pytest.raises(TypeError, match="ToolTemplate"):
        summary((), templates=invalid)


def test_validated_custom_template_can_be_summarised_without_global_registration() -> None:
    payload = {
        "key": "custom",
        "name": "Custom",
        "version": "1",
        "source_url": "https://example.org/custom",
        "content_note": "Project-specific tool.",
        "variants": [
            {
                "key": "default",
                "name": "Default",
                "domains": [
                    {
                        "key": "selection",
                        "name": "Selection",
                        "signalling_questions": [
                            {
                                "key": "representative",
                                "prompt": "Was selection representative?",
                                "allowed_answers": ["yes", "no"],
                            }
                        ],
                        "judgement_axes": [
                            {
                                "key": "risk_of_bias",
                                "name": "Risk of bias",
                                "allowed_judgements": [
                                    {"key": "low", "label": "Low risk"},
                                    {"key": "high", "label": "High risk"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    template = load_template_json(json.dumps(payload))
    assessment = DomainAssessment(
        record_id=uuid.UUID(int=10),
        tool_key="custom",
        variant_key="default",
        domain_key="selection",
        axis_key="risk_of_bias",
        judgement="high",
    )

    result = summary((assessment,), templates=(template,))

    assert result[0].tool_name == "Custom"
    assert tuple(item.count for item in result[0].counts) == (0, 1)


def test_default_templates_are_not_mutated_by_summary() -> None:
    before = BUILTIN_TEMPLATES
    summary(complete_assessment("rob2", "parallel_assignment", uuid.UUID(int=11)))
    assert before == BUILTIN_TEMPLATES
