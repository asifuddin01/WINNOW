"""Text field types shared by request bodies: length limits (guide 12.3) and no control
characters, so names and titles cannot smuggle line breaks into emails or spoof text
direction."""

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BeforeValidator, StringConstraints

# C0 controls and DEL, plus the Unicode bidirectional overrides and isolates.
_LINE_CONTROLS = re.compile(r"[\x00-\x1f\x7f‪-‮⁦-⁩]")
# The same, but tab, line feed and carriage return are fine in longer text.
_TEXT_CONTROLS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f‪-‮⁦-⁩]")


def _single_line(value: str) -> str:
    if _LINE_CONTROLS.search(value):
        raise ValueError("Use a single line of text without control characters.")
    return value


def _multi_line(value: str) -> str:
    if _TEXT_CONTROLS.search(value):
        raise ValueError("Remove the control characters from this text.")
    return value.replace("\r\n", "\n")


def _blank_to_none(value: object) -> object:
    """An emptied form field clears an optional value."""
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _line(max_length: int) -> StringConstraints:
    return StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length)


Title = Annotated[str, _line(300), AfterValidator(_single_line)]
Name = Annotated[str, _line(100), AfterValidator(_single_line)]
Term = Annotated[str, _line(200), AfterValidator(_single_line)]
CriterionText = Annotated[str, _line(1_000), AfterValidator(_multi_line)]
LongText = Annotated[str, _line(5_000), AfterValidator(_multi_line)]
OptionalLongText = Annotated[LongText | None, BeforeValidator(_blank_to_none)]
PicoText = Annotated[str, _line(2_000), AfterValidator(_multi_line)]
OptionalPicoText = Annotated[PicoText | None, BeforeValidator(_blank_to_none)]

# Named swatches rather than CSS values: the frontend maps each to colours that work in
# both themes, and nothing a user types ever reaches a style attribute.
Color = Literal["gray", "red", "orange", "amber", "green", "teal", "blue", "violet", "pink"]
