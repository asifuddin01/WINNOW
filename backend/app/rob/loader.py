"""Strict JSON loading for the bundled risk-of-bias template resources."""

import json
from importlib.resources import files
from types import MappingProxyType
from typing import cast

from app.rob.types import (
    Choice,
    DomainTemplate,
    JudgementAxis,
    SignallingQuestion,
    TemplateVariant,
    ToolTemplate,
)

type JsonObject = dict[str, object]

_TEMPLATE_FILES = ("rob2.json", "robins_i.json", "nos.json", "quadas2.json")


class TemplateValidationError(ValueError):
    """Raised when a template document is not valid against Winnow's strict schema."""


def _without_duplicate_keys(pairs: list[tuple[str, object]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            msg = f"duplicate JSON key: {key}"
            raise TemplateValidationError(msg)
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    msg = f"non-standard JSON constant is not permitted: {value}"
    raise TemplateValidationError(msg)


def _object(value: object, path: str) -> JsonObject:
    if type(value) is not dict:
        msg = f"{path} must be an object"
        raise TemplateValidationError(msg)
    return cast("JsonObject", value)


def _array(value: object, path: str) -> list[object]:
    if type(value) is not list:
        msg = f"{path} must be an array"
        raise TemplateValidationError(msg)
    return cast("list[object]", value)


def _string(value: object, path: str) -> str:
    if type(value) is not str:
        msg = f"{path} must be a string"
        raise TemplateValidationError(msg)
    return value


def _keys(value: JsonObject, expected: frozenset[str], path: str) -> None:
    actual = frozenset(value)
    if actual == expected:
        return
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    details: list[str] = []
    if missing:
        details.append(f"missing {missing}")
    if extra:
        details.append(f"unexpected {extra}")
    msg = f"{path} has invalid fields: {', '.join(details)}"
    raise TemplateValidationError(msg)


def _choice(value: object, path: str) -> Choice:
    item = _object(value, path)
    _keys(item, frozenset({"key", "label"}), path)
    return Choice(
        key=_string(item["key"], f"{path}.key"),
        label=_string(item["label"], f"{path}.label"),
    )


def _question(value: object, path: str) -> SignallingQuestion:
    item = _object(value, path)
    _keys(item, frozenset({"key", "prompt", "allowed_answers"}), path)
    answers = _array(item["allowed_answers"], f"{path}.allowed_answers")
    return SignallingQuestion(
        key=_string(item["key"], f"{path}.key"),
        prompt=_string(item["prompt"], f"{path}.prompt"),
        allowed_answers=tuple(
            _string(answer, f"{path}.allowed_answers[{index}]")
            for index, answer in enumerate(answers)
        ),
    )


def _axis(value: object, path: str) -> JudgementAxis:
    item = _object(value, path)
    _keys(item, frozenset({"key", "name", "allowed_judgements"}), path)
    judgements = _array(item["allowed_judgements"], f"{path}.allowed_judgements")
    return JudgementAxis(
        key=_string(item["key"], f"{path}.key"),
        name=_string(item["name"], f"{path}.name"),
        allowed_judgements=tuple(
            _choice(judgement, f"{path}.allowed_judgements[{index}]")
            for index, judgement in enumerate(judgements)
        ),
    )


def _domain(value: object, path: str) -> DomainTemplate:
    item = _object(value, path)
    _keys(
        item,
        frozenset({"key", "name", "signalling_questions", "judgement_axes"}),
        path,
    )
    questions = _array(item["signalling_questions"], f"{path}.signalling_questions")
    axes = _array(item["judgement_axes"], f"{path}.judgement_axes")
    return DomainTemplate(
        key=_string(item["key"], f"{path}.key"),
        name=_string(item["name"], f"{path}.name"),
        signalling_questions=tuple(
            _question(question, f"{path}.signalling_questions[{index}]")
            for index, question in enumerate(questions)
        ),
        judgement_axes=tuple(
            _axis(axis, f"{path}.judgement_axes[{index}]") for index, axis in enumerate(axes)
        ),
    )


def _variant(value: object, path: str) -> TemplateVariant:
    item = _object(value, path)
    _keys(item, frozenset({"key", "name", "domains"}), path)
    domains = _array(item["domains"], f"{path}.domains")
    return TemplateVariant(
        key=_string(item["key"], f"{path}.key"),
        name=_string(item["name"], f"{path}.name"),
        domains=tuple(
            _domain(domain, f"{path}.domains[{index}]") for index, domain in enumerate(domains)
        ),
    )


def _template(value: object) -> ToolTemplate:
    item = _object(value, "template")
    _keys(
        item,
        frozenset({"key", "name", "version", "source_url", "content_note", "variants"}),
        "template",
    )
    variants = _array(item["variants"], "template.variants")
    return ToolTemplate(
        key=_string(item["key"], "template.key"),
        name=_string(item["name"], "template.name"),
        version=_string(item["version"], "template.version"),
        source_url=_string(item["source_url"], "template.source_url"),
        content_note=_string(item["content_note"], "template.content_note"),
        variants=tuple(
            _variant(variant, f"template.variants[{index}]")
            for index, variant in enumerate(variants)
        ),
    )


def load_template_json(document: str, *, source: str = "<memory>") -> ToolTemplate:
    """Parse and validate one template JSON document.

    Inputs are a JSON string and a diagnostic source label; output is a deeply immutable
    ``ToolTemplate``. Complexity is O(c + n) time and space for c input characters and n
    schema nodes. Unknown fields, duplicate JSON keys and non-standard constants are rejected.
    The schema stores concise Winnow prompts rather than claiming to reproduce official tools.
    """

    if type(document) is not str:
        msg = "document must be a string"
        raise TypeError(msg)
    if type(source) is not str or not source.strip():
        msg = "source must be a nonblank string"
        raise TypeError(msg)
    try:
        decoded = json.loads(
            document,
            object_pairs_hook=_without_duplicate_keys,
            parse_constant=_reject_constant,
        )
        return _template(cast("object", decoded))
    except TemplateValidationError as error:
        msg = f"{source}: {error}"
        raise TemplateValidationError(msg) from error
    except (json.JSONDecodeError, RecursionError, TypeError, ValueError) as error:
        msg = f"{source}: {error}"
        raise TemplateValidationError(msg) from error


def _load_packaged_template(filename: str) -> ToolTemplate:
    resource = files("app.rob.templates").joinpath(filename)
    # Package-resource reads are the one deliberate I/O exception required by the queue.
    document = resource.read_text(encoding="utf-8")
    template = load_template_json(document, source=filename)
    if template.key != filename.removesuffix(".json"):
        msg = f"{filename}: template key must match its filename"
        raise TemplateValidationError(msg)
    return template


BUILTIN_TEMPLATES: tuple[ToolTemplate, ...] = tuple(
    _load_packaged_template(filename) for filename in _TEMPLATE_FILES
)

_templates = {template.key: template for template in BUILTIN_TEMPLATES}
if len(_templates) != len(BUILTIN_TEMPLATES):
    raise TemplateValidationError("built-in templates contain a duplicate tool key")
TEMPLATES_BY_KEY = MappingProxyType(_templates)


def get_template(tool_key: str) -> ToolTemplate:
    """Return one validated built-in template by key.

    Input is a built-in tool key and output is its immutable template; an unknown key raises
    ``KeyError``. Complexity is O(1) time and space. Custom templates are intentionally not
    registered globally; adapters pass validated custom values directly to ``summary``.
    """

    if type(tool_key) is not str:
        msg = "tool_key must be a string"
        raise TypeError(msg)
    return TEMPLATES_BY_KEY[tool_key]
