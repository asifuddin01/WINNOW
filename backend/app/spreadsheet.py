"""Cells for CSV and spreadsheet downloads that cannot run as formulas (CSV injection).

A cell starting with `=`, `+`, `-`, `@`, a tab or a carriage return is a formula to Excel
and LibreOffice; a leading apostrophe makes it text, and is not shown.
"""

FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_STARTS) else text
