"""Deterministic per-domain aggregation for risk-of-bias visualisations."""

import uuid
from collections import Counter
from collections.abc import Sequence

from app.rob.loader import BUILTIN_TEMPLATES
from app.rob.types import (
    DomainAssessment,
    DomainSummary,
    JudgementAxis,
    JudgementCount,
    TemplateVariant,
    ToolTemplate,
)

type GroupKey = tuple[str, str]
type CellKey = tuple[str, str]
type UnitKey = tuple[uuid.UUID, str, str]


def _template_index(templates: Sequence[ToolTemplate]) -> dict[str, ToolTemplate]:
    result: dict[str, ToolTemplate] = {}
    for template in templates:
        if type(template) is not ToolTemplate:
            msg = "templates must contain ToolTemplate values"
            raise TypeError(msg)
        if template.key in result:
            msg = f"templates contains duplicate tool key: {template.key}"
            raise ValueError(msg)
        result[template.key] = template
    return result


def _variant(template: ToolTemplate, variant_key: str) -> TemplateVariant | None:
    return next((variant for variant in template.variants if variant.key == variant_key), None)


def _allowed_axis(
    variant: TemplateVariant,
    domain_key: str,
    axis_key: str,
) -> JudgementAxis | None:
    for domain in variant.domains:
        if domain.key != domain_key:
            continue
        return next((axis for axis in domain.judgement_axes if axis.key == axis_key), None)
    return None


def _expected_cells(variant: TemplateVariant) -> frozenset[CellKey]:
    return frozenset(
        (domain.key, axis.key) for domain in variant.domains for axis in domain.judgement_axes
    )


def summary(
    assessments: Sequence[DomainAssessment],
    *,
    templates: Sequence[ToolTemplate] = BUILTIN_TEMPLATES,
) -> tuple[DomainSummary, ...]:
    """Fold complete record-level domain judgements into ordered plot-ready counts.

    Inputs are one final judgement per record/domain/axis and validated built-in or custom
    templates. Output has one row per used domain axis, retains template/judgement order and
    includes zero-count choices. Complexity is O(a + s) time and space for a assessments and
    s emitted summary cells. Duplicate, unknown, mixed-variant or incomplete records raise
    errors rather than biasing percentages. NOS stars remain ordinal counts because the
    official instrument defines no universal traffic-light conversion.
    """

    template_by_key = _template_index(templates)
    received: dict[UnitKey, set[CellKey]] = {}
    units_by_group: dict[GroupKey, set[uuid.UUID]] = {}
    variant_by_record_tool: dict[tuple[uuid.UUID, str], str] = {}
    expected_by_group: dict[GroupKey, frozenset[CellKey]] = {}
    seen: set[tuple[uuid.UUID, str, str, str, str]] = set()
    counts: Counter[tuple[str, str, str, str, str]] = Counter()

    for assessment in assessments:
        if type(assessment) is not DomainAssessment:
            msg = "assessments must contain DomainAssessment values"
            raise TypeError(msg)
        template = template_by_key.get(assessment.tool_key)
        if template is None:
            msg = f"unknown risk-of-bias tool: {assessment.tool_key}"
            raise ValueError(msg)
        matching_variant = _variant(template, assessment.variant_key)
        if matching_variant is None:
            msg = f"unknown variant for {assessment.tool_key}: {assessment.variant_key}"
            raise ValueError(msg)
        axis = _allowed_axis(
            matching_variant,
            assessment.domain_key,
            assessment.axis_key,
        )
        if axis is None:
            msg = (
                f"unknown domain axis for {assessment.tool_key}/{assessment.variant_key}: "
                f"{assessment.domain_key}/{assessment.axis_key}"
            )
            raise ValueError(msg)
        allowed = {choice.key for choice in axis.allowed_judgements}
        if assessment.judgement not in allowed:
            msg = (
                f"invalid judgement for {assessment.tool_key}/{assessment.domain_key}/"
                f"{assessment.axis_key}: {assessment.judgement}"
            )
            raise ValueError(msg)

        record_tool = (assessment.record_id, assessment.tool_key)
        previous_variant = variant_by_record_tool.setdefault(record_tool, assessment.variant_key)
        if previous_variant != assessment.variant_key:
            msg = "one record/tool assessment cannot mix template variants"
            raise ValueError(msg)

        unique_cell = (
            assessment.record_id,
            assessment.tool_key,
            assessment.variant_key,
            assessment.domain_key,
            assessment.axis_key,
        )
        if unique_cell in seen:
            msg = "a record may have only one judgement per tool/domain axis"
            raise ValueError(msg)
        seen.add(unique_cell)

        unit = (assessment.record_id, assessment.tool_key, assessment.variant_key)
        received.setdefault(unit, set()).add((assessment.domain_key, assessment.axis_key))
        group = (assessment.tool_key, assessment.variant_key)
        units_by_group.setdefault(group, set()).add(assessment.record_id)
        expected_by_group.setdefault(group, _expected_cells(matching_variant))
        counts[
            (
                assessment.tool_key,
                assessment.variant_key,
                assessment.domain_key,
                assessment.axis_key,
                assessment.judgement,
            )
        ] += 1

    for unit in sorted(received, key=lambda item: (item[0].int, item[1], item[2])):
        _, tool_key, variant_key = unit
        expected = expected_by_group[(tool_key, variant_key)]
        missing = sorted(expected - received[unit])
        if missing:
            detail = ", ".join(f"{domain}/{axis}" for domain, axis in missing)
            msg = f"record assessment is incomplete; missing: {detail}"
            raise ValueError(msg)

    output: list[DomainSummary] = []
    for template in templates:
        for variant in template.variants:
            group = (template.key, variant.key)
            if group not in units_by_group:
                continue
            total = len(units_by_group[group])
            for domain in variant.domains:
                for axis in domain.judgement_axes:
                    output.append(
                        DomainSummary(
                            tool_key=template.key,
                            tool_name=template.name,
                            variant_key=variant.key,
                            variant_name=variant.name,
                            domain_key=domain.key,
                            domain_name=domain.name,
                            axis_key=axis.key,
                            axis_name=axis.name,
                            counts=tuple(
                                JudgementCount(
                                    judgement=choice.key,
                                    label=choice.label,
                                    count=counts[
                                        (
                                            template.key,
                                            variant.key,
                                            domain.key,
                                            axis.key,
                                            choice.key,
                                        )
                                    ],
                                )
                                for choice in axis.allowed_judgements
                            ),
                            total=total,
                        )
                    )
    return tuple(output)
