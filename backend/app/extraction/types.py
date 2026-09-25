"""An extraction form's fields, and the problems a form or an entry can have."""

from dataclasses import dataclass, field
from typing import Literal

FieldType = Literal[
    "short_text",
    "long_text",
    "number",
    "select",
    "multi_select",
    "yes_no_unclear",
    "date",
    "table",
    "section",
]
FIELD_TYPES: tuple[FieldType, ...] = (
    "short_text",
    "long_text",
    "number",
    "select",
    "multi_select",
    "yes_no_unclear",
    "date",
    "table",
    "section",
)
# The types a table's columns may have: a cell holds one value.
SCALAR_TYPES: tuple[FieldType, ...] = (
    "short_text",
    "long_text",
    "number",
    "select",
    "multi_select",
    "yes_no_unclear",
    "date",
)
YES_NO_UNCLEAR = ("yes", "no", "unclear")


@dataclass(frozen=True, slots=True)
class Field:
    """One field of a form. A `section` is a heading and holds no value; a `table` holds
    rows whose cells are its `columns`."""

    key: str
    label: str
    type: FieldType
    help: str | None = None
    required: bool = False
    options: tuple[str, ...] = ()
    unit: str | None = None
    integer: bool = False
    minimum: float | None = None
    maximum: float | None = None
    columns: tuple["Field", ...] = ()
    min_rows: int = 0
    max_rows: int | None = None


@dataclass(frozen=True, slots=True)
class FormSchema:
    fields: tuple[Field, ...] = ()

    def values(self) -> tuple[Field, ...]:
        """The fields that hold a value (all but sections)."""
        return tuple(item for item in self.fields if item.type != "section")


class SchemaError(ValueError):
    """The form cannot be used; every problem is listed, in words."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


class EntryError(ValueError):
    """What is wrong with an entry, keyed by field (`outcomes[2].mean` for a table cell)."""

    def __init__(self, problems: dict[str, str]) -> None:
        super().__init__("; ".join(f"{key}: {text}" for key, text in problems.items()))
        self.problems = problems


@dataclass(frozen=True, slots=True)
class Difference:
    """A value two extractors gave differently; `path` is `key` or `key[row].column`."""

    path: str
    label: str
    a: object
    b: object


@dataclass(frozen=True, slots=True)
class EntryForExport:
    record_id: str
    record_label: str
    # The extractor's name, or "consensus".
    extractor: str
    data: dict[str, object] = field(default_factory=dict)
