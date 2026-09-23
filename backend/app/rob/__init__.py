"""Validated risk-of-bias templates and deterministic summary aggregation."""

from app.rob.aggregation import summary
from app.rob.loader import (
    BUILTIN_TEMPLATES,
    TEMPLATES_BY_KEY,
    TemplateValidationError,
    get_template,
    load_template_json,
)
from app.rob.types import (
    Choice,
    DomainAssessment,
    DomainSummary,
    DomainTemplate,
    JudgementAxis,
    JudgementCount,
    SignallingQuestion,
    TemplateVariant,
    ToolTemplate,
)

__all__ = [
    "BUILTIN_TEMPLATES",
    "TEMPLATES_BY_KEY",
    "Choice",
    "DomainAssessment",
    "DomainSummary",
    "DomainTemplate",
    "JudgementAxis",
    "JudgementCount",
    "SignallingQuestion",
    "TemplateValidationError",
    "TemplateVariant",
    "ToolTemplate",
    "get_template",
    "load_template_json",
    "summary",
]
