"""Extracted data laid out for analysis (guide 8.12): long or wide.

Long has one row per value, which R's tidyverse and Stata's `reshape` start from; wide
has one row per study and extractor, a column per field and `key[row].column` for table
cells, which RevMan and spreadsheets read directly. A multi-select is joined with "; ";
sections produce nothing.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.extraction.types import EntryForExport, FormSchema

ENTRY_COLUMNS = ("record_id", "study", "extractor")
LONG_COLUMNS = (*ENTRY_COLUMNS, "field", "label", "row", "column", "value", "unit")


def _rows(value: object) -> int:
    return len(value) if isinstance(value, list) else 0


def _cell(value: object) -> object:
    return "; ".join(str(item) for item in value) if isinstance(value, list) else value


def long_rows(schema: FormSchema, entries: Sequence[EntryForExport]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for entry in entries:
        base = {
            "record_id": entry.record_id,
            "study": entry.record_label,
            "extractor": entry.extractor,
        }
        for field in schema.values():
            value = entry.data.get(field.key)
            if value is None:
                continue
            if field.type != "table":
                rows.append(
                    {
                        **base,
                        "field": field.key,
                        "label": field.label,
                        "row": "",
                        "column": "",
                        "value": _cell(value),
                        "unit": field.unit or "",
                    }
                )
                continue
            for number, row in enumerate(value if isinstance(value, list) else [], start=1):
                for column in field.columns:
                    if row.get(column.key) is None:
                        continue
                    rows.append(
                        {
                            **base,
                            "field": field.key,
                            "label": f"{field.label}: {column.label}",
                            "row": number,
                            "column": column.key,
                            "value": _cell(row[column.key]),
                            "unit": column.unit or "",
                        }
                    )
    return rows


@dataclass(frozen=True, slots=True)
class Wide:
    headers: list[str]
    rows: list[dict[str, object]]


def wide_rows(schema: FormSchema, entries: Sequence[EntryForExport]) -> Wide:
    """One row per entry; a table gets as many row groups as the longest one present."""
    headers = list(ENTRY_COLUMNS)
    longest = {
        field.key: max((_rows(entry.data.get(field.key)) for entry in entries), default=0)
        for field in schema.values()
        if field.type == "table"
    }
    for field in schema.values():
        if field.type != "table":
            headers.append(field.key)
            continue
        for number in range(1, longest[field.key] + 1):
            headers += [f"{field.key}[{number}].{column.key}" for column in field.columns]
    rows = []
    for entry in entries:
        row: dict[str, object] = dict.fromkeys(headers, "")
        row.update(record_id=entry.record_id, study=entry.record_label, extractor=entry.extractor)
        for field in schema.values():
            value = entry.data.get(field.key)
            if value is None:
                continue
            if field.type != "table":
                row[field.key] = _cell(value)
                continue
            for number, cells in enumerate(value if isinstance(value, list) else [], start=1):
                for column in field.columns:
                    if cells.get(column.key) is not None:
                        row[f"{field.key}[{number}].{column.key}"] = _cell(cells[column.key])
        rows.append(row)
    return Wide(headers=headers, rows=rows)
