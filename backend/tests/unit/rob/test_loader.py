"""Template JSON loading is strict, contextual and safe for future custom tools."""

import copy
import json
import sys
from typing import cast

import pytest

from app.rob import TemplateValidationError, load_template_json


def valid_payload() -> dict[str, object]:
    return {
        "key": "custom_tool",
        "name": "Custom tool",
        "version": "1",
        "source_url": "https://example.org/tool",
        "content_note": "Review-specific example template.",
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
                                "prompt": "Was the sample representative?",
                                "allowed_answers": ["yes", "no", "unclear"],
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


def encode(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False)


def test_valid_custom_template_is_loaded_into_frozen_objects() -> None:
    template = load_template_json(encode(valid_payload()), source="custom.json")

    assert template.key == "custom_tool"
    assert template.variants[0].domains[0].signalling_questions[0].allowed_answers == (
        "yes",
        "no",
        "unclear",
    )


@pytest.mark.parametrize(
    "document",
    [
        "{",
        "[]",
        '{"key":"a","key":"b"}',
        encode({**valid_payload(), "unexpected": True}),
        encode({key: value for key, value in valid_payload().items() if key != "version"}),
    ],
)
def test_malformed_duplicate_or_wrong_shape_documents_are_rejected(document: str) -> None:
    with pytest.raises(TemplateValidationError, match=r"custom\.json"):
        load_template_json(document, source="custom.json")


def test_nonstandard_json_constants_are_rejected() -> None:
    document = encode(valid_payload()).replace('"version": "1"', '"version": NaN')
    with pytest.raises(TemplateValidationError, match="non-standard JSON constant"):
        load_template_json(document)


def test_excessively_nested_json_is_reported_as_a_validation_error() -> None:
    depth = sys.getrecursionlimit() + 100
    document = "[" * depth + "]" * depth
    with pytest.raises(TemplateValidationError, match=r"deep\.json"):
        load_template_json(document, source="deep.json")


@pytest.mark.parametrize(
    ("path", "replacement", "message"),
    [
        (("variants",), [], "variants must not be empty"),
        (("variants", 0, "domains"), [], "domains must not be empty"),
        (
            ("variants", 0, "domains", 0, "signalling_questions"),
            [],
            "signalling_questions must not be empty",
        ),
        (
            ("variants", 0, "domains", 0, "judgement_axes"),
            [],
            "judgement_axes must not be empty",
        ),
        (
            (
                "variants",
                0,
                "domains",
                0,
                "signalling_questions",
                0,
                "allowed_answers",
            ),
            [],
            "allowed_answers must not be empty",
        ),
        (
            (
                "variants",
                0,
                "domains",
                0,
                "judgement_axes",
                0,
                "allowed_judgements",
            ),
            [],
            "allowed_judgements must not be empty",
        ),
    ],
)
def test_empty_required_collections_are_rejected(
    path: tuple[str | int, ...], replacement: object, message: str
) -> None:
    payload = copy.deepcopy(valid_payload())
    target: object = payload
    for component in path[:-1]:
        target = target[component]  # type: ignore[index]
    target[path[-1]] = replacement  # type: ignore[index]

    with pytest.raises(TemplateValidationError, match=message):
        load_template_json(encode(payload))


@pytest.mark.parametrize(
    ("path", "replacement", "message"),
    [
        (("key",), "Not valid", "snake-case"),
        (("name",), " ", "must not be blank"),
        (("source_url",), "http://example.org/tool", "HTTPS URL"),
        (("source_url",), "https://user@example.org/tool", "without credentials"),
        (("content_note",), "bad\u0000note", "control characters"),
        (("variants", 0, "name"), 12, "must be a string"),
    ],
)
def test_invalid_scalar_values_are_rejected(
    path: tuple[str | int, ...], replacement: object, message: str
) -> None:
    payload = copy.deepcopy(valid_payload())
    target: object = payload
    for component in path[:-1]:
        target = target[component]  # type: ignore[index]
    target[path[-1]] = replacement  # type: ignore[index]

    with pytest.raises(TemplateValidationError, match=message):
        load_template_json(encode(payload))


@pytest.mark.parametrize(
    ("collection_path", "message"),
    [
        (("variants",), "duplicate key"),
        (("variants", 0, "domains"), "duplicate key"),
        (("variants", 0, "domains", 0, "signalling_questions"), "duplicate key"),
        (("variants", 0, "domains", 0, "judgement_axes"), "duplicate key"),
        (
            ("variants", 0, "domains", 0, "judgement_axes", 0, "allowed_judgements"),
            "duplicate key",
        ),
    ],
)
def test_duplicate_nested_keys_are_rejected(
    collection_path: tuple[str | int, ...], message: str
) -> None:
    payload = copy.deepcopy(valid_payload())
    target: object = payload
    for component in collection_path:
        target = target[component]  # type: ignore[index]
    assert isinstance(target, list)
    target.append(copy.deepcopy(target[0]))

    with pytest.raises(TemplateValidationError, match=message):
        load_template_json(encode(payload))


def test_duplicate_allowed_answer_values_are_rejected() -> None:
    payload = valid_payload()
    question = payload["variants"][0]["domains"][0]["signalling_questions"][0]  # type: ignore[index]
    question["allowed_answers"] = ["yes", "yes"]
    with pytest.raises(TemplateValidationError, match="duplicate value"):
        load_template_json(encode(payload))


def test_unknown_nested_fields_are_rejected_at_their_path() -> None:
    payload = valid_payload()
    domain = payload["variants"][0]["domains"][0]  # type: ignore[index]
    domain["unknown"] = "value"
    with pytest.raises(TemplateValidationError, match=r"domains\[0\].*unexpected"):
        load_template_json(encode(payload))


def test_document_and_source_require_plain_strings() -> None:
    with pytest.raises(TypeError, match="document must be a string"):
        load_template_json(cast("str", 42))
    with pytest.raises(TypeError, match="source must be a nonblank string"):
        load_template_json(encode(valid_payload()), source=" ")
