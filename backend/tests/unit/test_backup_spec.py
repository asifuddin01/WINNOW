"""The backup format's values: written as JSON, read back as their column's type, and
anything that does not fit refused."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from ipaddress import IPv4Address
from typing import Any

import pytest
from sqlalchemy import ARRAY, Boolean, Date, DateTime, Float, Integer, Text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.types import TypeEngine

from app.backup.spec import BY_NAME, TABLES, BackupFormatError, columns, from_json, to_json
from app.models import DecisionValue, Record
from app.models.base import pg_enum

MOMENT = datetime(2026, 9, 25, 8, 30, tzinfo=UTC)


def test_values_are_written_as_plain_json() -> None:
    record_id = uuid.uuid4()
    written = to_json(
        {
            "id": record_id,
            "when": MOMENT,
            "day": date(2026, 9, 25),
            "decision": DecisionValue.INCLUDE,
            "ip": IPv4Address("10.0.0.1"),
            "tags": ("a", "b"),
            "nothing": None,
        }
    )
    assert written == {
        "id": str(record_id),
        "when": "2026-09-25T08:30:00+00:00",
        "day": "2026-09-25",
        "decision": "include",
        "ip": "10.0.0.1",
        "tags": ["a", "b"],
        "nothing": None,
    }
    with pytest.raises(TypeError, match="Decimal cannot go in a backup"):
        to_json(Decimal(1))


@pytest.mark.parametrize(
    ("type_", "value", "expected"),
    [
        (JSONB(), {"any": ["thing"]}, {"any": ["thing"]}),
        (ARRAY(Text()), ["a", "b"], ["a", "b"]),
        (pg_enum(DecisionValue, "decision_value"), "exclude", DecisionValue.EXCLUDE),
        (Boolean(), True, True),
        (Integer(), 3, 3),
        (Float(), 1, 1.0),
        (DateTime(timezone=True), "2026-09-25T08:30:00+00:00", MOMENT),
        (Date(), "2026-09-25", date(2026, 9, 25)),
        (INET(), "10.0.0.1", "10.0.0.1"),
        (
            UUID(),
            "0199a0a0-0000-7000-8000-000000000001",
            uuid.UUID(int=0x0199A0A0000070008000000000000001),
        ),
        (Text(), "words", "words"),
        (Integer(), None, None),
    ],
)
def test_values_are_read_back_as_their_column_type(
    type_: TypeEngine[Any], value: Any, expected: Any
) -> None:
    assert from_json(type_, value, "t.c") == expected


@pytest.mark.parametrize(
    ("type_", "value", "problem"),
    [
        (ARRAY(Text()), "a", "t.c should be a list"),
        (Boolean(), "yes", "t.c should be true or false"),
        (Integer(), True, "t.c should be a whole number"),
        (Integer(), 1.5, "t.c should be a whole number"),
        (Float(), "1", "t.c should be a number"),
        (Text(), 5, "t.c should be text"),
        (pg_enum(DecisionValue, "decision_value"), "perhaps", "t.c is not valid"),
        (DateTime(timezone=True), "yesterday", "t.c is not valid"),
        (UUID(), "not-an-id", "t.c is not valid"),
    ],
)
def test_a_value_of_the_wrong_type_is_refused(
    type_: TypeEngine[Any], value: Any, problem: str
) -> None:
    with pytest.raises(BackupFormatError, match=problem):
        from_json(type_, value, "t.c")


def test_every_table_comes_after_the_tables_it_points_to() -> None:
    seen = {"project", "people"}
    for spec in TABLES:
        for target in [*spec.refs.values(), *spec.id_arrays.values()]:
            assert target in seen or target == spec.name, f"{spec.name} → {target}"
        seen.add(spec.name)
    assert set(BY_NAME) == {spec.name for spec in TABLES}


def test_columns_the_database_works_out_are_not_carried() -> None:
    carried = columns(Record.__table__)  # type: ignore[arg-type]
    assert "title" in carried
    assert "search_vector" not in carried
    assert "authors_text" not in carried
