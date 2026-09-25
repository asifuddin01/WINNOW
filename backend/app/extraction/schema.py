"""A form's schema as JSON (stored, and sent by the builder) and back.

    {"fields": [
      {"key": "design", "label": "Study design", "type": "select", "required": true,
       "options": ["RCT", "Cohort"]},
      {"key": "n", "label": "Participants", "type": "number", "unit": "people",
       "integer": true, "minimum": 0},
      {"key": "outcomes", "label": "Outcomes per arm", "type": "table", "max_rows": 20,
       "columns": [{"key": "arm", "label": "Arm", "type": "short_text"},
                   {"key": "mean", "label": "Mean", "type": "number"}]}
    ]}

`parse_schema` checks everything and lists every problem at once, so the builder can
show them all.
"""

import math
import re
from typing import Any

from app.extraction.types import FIELD_TYPES, SCALAR_TYPES, Field, FormSchema, SchemaError

KEY = re.compile(r"[a-z][a-z0-9_]{0,39}")
MAX_FIELDS = 200
MAX_OPTIONS = 100
MAX_COLUMNS = 30
MAX_ROWS = 500
MAX_LABEL = 300
MAX_HELP = 2_000
MAX_OPTION = 200
MAX_UNIT = 50
WITH_OPTIONS = ("select", "multi_select")
ATTRIBUTES = {
    "key",
    "label",
    "type",
    "help",
    "required",
    "options",
    "unit",
    "integer",
    "minimum",
    "maximum",
    "columns",
    "min_rows",
    "max_rows",
}


def parse_schema(raw: object) -> FormSchema:
    problems: list[str] = []
    if not isinstance(raw, dict) or not isinstance(raw.get("fields"), list):
        raise SchemaError(['A form is an object with a list of "fields".'])
    unknown = set(raw) - {"fields"}
    if unknown:
        problems.append(f"The form has settings Winnow does not know: {sorted(unknown)}.")
    items: list[Any] = raw["fields"]
    if len(items) > MAX_FIELDS:
        problems.append(f"A form has at most {MAX_FIELDS} fields; this one has {len(items)}.")
    fields = tuple(
        field
        for index, item in enumerate(items[:MAX_FIELDS])
        if (field := _field(item, f"Field {index + 1}", problems, in_table=False)) is not None
    )
    _unique([field.key for field in fields], "fields", problems)
    if problems:
        raise SchemaError(problems)
    return FormSchema(fields=fields)


def _unique(keys: list[str], what: str, problems: list[str]) -> None:
    """`what` is plural: "fields", "columns of 'Arms'"."""
    seen: set[str] = set()
    for key in keys:
        if key in seen:
            problems.append(f"Two {what} have the key {key!r}; each needs its own.")
        seen.add(key)


def _field(item: object, where: str, problems: list[str], *, in_table: bool) -> Field | None:
    if not isinstance(item, dict):
        problems.append(f"{where} is not a field.")
        return None
    start = len(problems)
    unknown = set(item) - ATTRIBUTES
    if unknown:
        problems.append(f"{where} has settings Winnow does not know: {sorted(unknown)}.")
    key = item.get("key")
    if not isinstance(key, str) or not KEY.fullmatch(key):
        problems.append(
            f"{where}: the key must start with a lowercase letter and hold only lowercase "
            "letters, digits and underscores (40 at most)."
        )
    label = item.get("label")
    if not isinstance(label, str) or not label.strip():
        problems.append(f"{where} needs a label.")
    elif len(label) > MAX_LABEL:
        problems.append(f"{where}: a label has at most {MAX_LABEL} characters.")
    else:
        where = f"{label.strip()!r}"
    kind = item.get("type")
    allowed = SCALAR_TYPES if in_table else FIELD_TYPES
    if kind not in allowed:
        problems.append(
            f"{where}: a table column cannot be a {kind}."
            if in_table and kind in FIELD_TYPES
            else f"{where} has no type Winnow knows ({kind!r})."
        )
    help_text = item.get("help")
    if help_text is not None and (not isinstance(help_text, str) or len(help_text) > MAX_HELP):
        problems.append(f"{where}: help text has at most {MAX_HELP} characters.")
    required = item.get("required", False)
    integer = item.get("integer", False)
    for name, flag in (("required", required), ("integer", integer)):
        if not isinstance(flag, bool):
            problems.append(f"{where}: {name} is true or false.")

    options = item.get("options", [])
    if not isinstance(options, list) or not all(isinstance(o, str) for o in options):
        problems.append(f"{where}: options are a list of words.")
        options = []
    cleaned = [option.strip() for option in options]
    if kind in WITH_OPTIONS:
        if not cleaned:
            problems.append(f"{where} needs at least one option.")
        if len(cleaned) > MAX_OPTIONS:
            problems.append(f"{where}: at most {MAX_OPTIONS} options.")
        if any(not option for option in cleaned):
            problems.append(f"{where} has an empty option.")
        if any(len(option) > MAX_OPTION for option in cleaned):
            problems.append(f"{where}: an option has at most {MAX_OPTION} characters.")
        if len(set(cleaned)) != len(cleaned):
            problems.append(f"{where} lists an option twice.")
    elif cleaned:
        problems.append(f"{where}: only select fields have options.")

    unit = item.get("unit")
    if unit is not None and (kind != "number" or not isinstance(unit, str) or len(unit) > MAX_UNIT):
        problems.append(f"{where}: only numbers have a unit, of {MAX_UNIT} characters at most.")
    if integer and kind != "number":
        problems.append(f"{where}: only numbers can be whole numbers.")
    bounds: list[float | None] = []
    for name in ("minimum", "maximum"):
        bound = item.get(name)
        if bound is None:
            bounds.append(None)
            continue
        if kind != "number":
            problems.append(f"{where}: only numbers have a {name}.")
        if (
            isinstance(bound, bool)
            or not isinstance(bound, int | float)
            or not math.isfinite(bound)
        ):
            problems.append(f"{where}: the {name} must be a number.")
            bounds.append(None)
        else:
            bounds.append(float(bound))
    minimum, maximum = bounds
    if minimum is not None and maximum is not None and minimum > maximum:
        problems.append(f"{where}: the minimum is above the maximum.")

    columns: tuple[Field, ...] = ()
    raw_columns = item.get("columns", [])
    min_rows, max_rows = item.get("min_rows", 0), item.get("max_rows")
    if kind == "table":
        if not isinstance(raw_columns, list) or not raw_columns:
            problems.append(f"{where}: a table needs at least one column.")
            raw_columns = []
        if len(raw_columns) > MAX_COLUMNS:
            problems.append(f"{where}: a table has at most {MAX_COLUMNS} columns.")
        columns = tuple(
            column
            for index, raw in enumerate(raw_columns[:MAX_COLUMNS])
            if (column := _field(raw, f"{where}, column {index + 1}", problems, in_table=True))
            is not None
        )
        _unique([column.key for column in columns], f"columns of {where}", problems)
        if isinstance(min_rows, bool) or not isinstance(min_rows, int) or min_rows < 0:
            problems.append(f"{where}: the fewest rows is a whole number, 0 or more.")
            min_rows = 0
        if max_rows is not None and (
            isinstance(max_rows, bool)
            or not isinstance(max_rows, int)
            or not max(1, min_rows) <= max_rows <= MAX_ROWS
        ):
            problems.append(
                f"{where}: the most rows is a whole number from {max(1, min_rows)} to {MAX_ROWS}."
            )
            max_rows = None
    elif raw_columns or item.get("min_rows") is not None or max_rows is not None:
        problems.append(f"{where}: only tables have columns and rows.")

    if len(problems) > start:
        return None
    return Field(
        key=str(key),
        label=str(label).strip(),
        type=kind,  # type: ignore[arg-type]  # checked against FIELD_TYPES above
        help=help_text.strip() or None if isinstance(help_text, str) else None,
        required=bool(required),
        options=tuple(cleaned) if kind in WITH_OPTIONS else (),
        unit=unit.strip() or None if isinstance(unit, str) else None,
        integer=bool(integer),
        minimum=minimum,
        maximum=maximum,
        columns=columns,
        min_rows=int(min_rows) if kind == "table" else 0,
        max_rows=max_rows if kind == "table" else None,
    )


def schema_to_json(schema: FormSchema) -> dict[str, Any]:
    """The schema as stored: defaults left out, so `parse_schema` gives it back unchanged."""
    return {"fields": [_field_json(field) for field in schema.fields]}


def _field_json(field: Field) -> dict[str, Any]:
    out: dict[str, Any] = {"key": field.key, "label": field.label, "type": field.type}
    if field.help:
        out["help"] = field.help
    if field.required:
        out["required"] = True
    if field.options:
        out["options"] = list(field.options)
    if field.unit:
        out["unit"] = field.unit
    if field.integer:
        out["integer"] = True
    for name in ("minimum", "maximum"):
        value = getattr(field, name)
        if value is not None:
            out[name] = int(value) if value.is_integer() else value
    if field.type == "table":
        out["columns"] = [_field_json(column) for column in field.columns]
        if field.min_rows:
            out["min_rows"] = field.min_rows
        if field.max_rows is not None:
            out["max_rows"] = field.max_rows
    return out
