"""What an extractor types into a form: checked, normalised, and compared with another's.

Values are normalised so that two people who typed the same thing agree: text is
stripped, numbers are numbers, a multi-select is in the form's order. Empty values are
dropped, so "nothing" is always absent rather than "", [] or None. A draft may be partial;
submitting (`complete=True`) enforces required fields and a table's fewest rows.
"""

import math
from datetime import date
from typing import Any

from app.extraction.types import (
    YES_NO_UNCLEAR,
    Difference,
    EntryError,
    Field,
    FormSchema,
)

MAX_SHORT = 500
MAX_LONG = 20_000


def validate_entry(schema: FormSchema, data: object, *, complete: bool) -> dict[str, object]:
    if not isinstance(data, dict):
        raise EntryError({"": "An entry is an object of field values."})
    problems: dict[str, str] = {}
    fields = {field.key: field for field in schema.values()}
    for key in data:
        if key not in fields:
            problems[str(key)] = "This form has no such field."
    out: dict[str, object] = {}
    for key, field in fields.items():
        if field.type == "table":
            rows = _table(field, data.get(key), key, problems, complete=complete)
            if rows:
                out[key] = rows
            continue
        value = _value(field, data.get(key), key, problems)
        if value is None:
            if complete and field.required and key not in problems:
                problems[key] = "Required."
            continue
        out[key] = value
    if problems:
        raise EntryError(problems)
    return out


def _table(
    field: Field, raw: object, path: str, problems: dict[str, str], *, complete: bool
) -> list[dict[str, object]]:
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        problems[path] = "A table is a list of rows."
        return []
    columns = {column.key: column for column in field.columns}
    rows: list[dict[str, object]] = []
    for number, row in enumerate(raw, start=1):
        where = f"{path}[{number}]"
        if not isinstance(row, dict):
            problems[where] = "A row is an object of cell values."
            continue
        for key in row:
            if key not in columns:
                problems[f"{where}.{key}"] = "This table has no such column."
        cells: dict[str, object] = {}
        missing: list[str] = []
        for key, column in columns.items():
            value = _value(column, row.get(key), f"{where}.{key}", problems)
            if value is None:
                if column.required and f"{where}.{key}" not in problems:
                    missing.append(f"{where}.{key}")
                continue
            cells[key] = value
        # An empty row is not a row: it is dropped, does not count, and misses nothing.
        if not cells:
            continue
        if complete:
            problems.update(dict.fromkeys(missing, "Required."))
        rows.append(cells)
    if field.max_rows is not None and len(rows) > field.max_rows:
        problems[path] = f"At most {field.max_rows} rows."
    elif complete and len(rows) < max(field.min_rows, 1 if field.required else 0):
        needed = max(field.min_rows, 1)
        problems[path] = f"At least {needed} row{'s' if needed != 1 else ''}."
    return rows


def _value(field: Field, raw: object, path: str, problems: dict[str, str]) -> object:
    """The normalised value, or None when empty (a problem is recorded when wrong)."""
    if raw is None:
        return None
    kind = field.type
    if kind in ("short_text", "long_text"):
        if not isinstance(raw, str):
            problems[path] = "Should be text."
            return None
        text = raw.strip()
        limit = MAX_SHORT if kind == "short_text" else MAX_LONG
        if len(text) > limit:
            problems[path] = f"At most {limit:,} characters."
            return None
        return text or None
    if kind == "number":
        return _number(field, raw, path, problems)
    if kind == "select":
        if raw == "":
            return None
        if raw not in field.options:
            problems[path] = "Choose one of the options."
            return None
        return raw
    if kind == "multi_select":
        if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
            problems[path] = "Should be a list of options."
            return None
        if any(item not in field.options for item in raw):
            problems[path] = "Choose from the options."
            return None
        if len(set(raw)) != len(raw):
            problems[path] = "An option is chosen twice."
            return None
        chosen = [option for option in field.options if option in raw]
        return chosen or None
    if kind == "yes_no_unclear":
        if raw == "":
            return None
        if raw not in YES_NO_UNCLEAR:
            problems[path] = "Yes, no or unclear."
            return None
        return raw
    if kind == "date":
        if raw == "":
            return None
        if not isinstance(raw, str):
            problems[path] = "Should be a date."
            return None
        try:
            if len(raw) != len("2026-01-31"):
                raise ValueError(raw)
            return date.fromisoformat(raw).isoformat()
        except ValueError:
            problems[path] = "Should be a real date, as YYYY-MM-DD."
            return None
    problems[path] = "This field holds no value."
    return None


def _number(field: Field, raw: object, path: str, problems: dict[str, str]) -> object:
    if raw == "":
        return None
    value: float
    if isinstance(raw, bool):
        problems[path] = "Should be a number."
        return None
    if isinstance(raw, int | float):
        value = float(raw)
    elif isinstance(raw, str):
        try:
            value = float(raw.strip().replace(",", ""))
        except ValueError:
            problems[path] = "Should be a number."
            return None
    else:
        problems[path] = "Should be a number."
        return None
    if not math.isfinite(value):
        problems[path] = "Should be a number."
        return None
    if field.integer and not value.is_integer():
        problems[path] = "Should be a whole number."
        return None
    if field.minimum is not None and value < field.minimum:
        problems[path] = f"At least {_shown(field.minimum)}."
        return None
    if field.maximum is not None and value > field.maximum:
        problems[path] = f"At most {_shown(field.maximum)}."
        return None
    # 12, "12" and 12.0 are one value: whole numbers are stored as whole numbers.
    return int(value) if value.is_integer() else value


def _shown(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def differences(schema: FormSchema, a: dict[str, Any], b: dict[str, Any]) -> list[Difference]:
    """Every value the two entries give differently, in form order; tables cell by cell.
    Two empty values do not differ."""
    found: list[Difference] = []
    for field in schema.values():
        if field.type != "table":
            if a.get(field.key) != b.get(field.key):
                found.append(Difference(field.key, field.label, a.get(field.key), b.get(field.key)))
            continue
        rows_a: list[dict[str, Any]] = a.get(field.key) or []
        rows_b: list[dict[str, Any]] = b.get(field.key) or []
        for index in range(max(len(rows_a), len(rows_b))):
            row_a = rows_a[index] if index < len(rows_a) else {}
            row_b = rows_b[index] if index < len(rows_b) else {}
            for column in field.columns:
                left, right = row_a.get(column.key), row_b.get(column.key)
                if left != right:
                    found.append(
                        Difference(
                            f"{field.key}[{index + 1}].{column.key}",
                            f"{field.label}, row {index + 1}: {column.label}",
                            left,
                            right,
                        )
                    )
    return found
