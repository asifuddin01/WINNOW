"""Extraction forms (guide 8.12): schemas, entries, differences and export layouts."""

from typing import Any

import pytest

from app.extraction import (
    LONG_COLUMNS,
    EntryError,
    EntryForExport,
    SchemaError,
    differences,
    long_rows,
    parse_schema,
    schema_to_json,
    validate_entry,
    wide_rows,
)

TRIAL: dict[str, Any] = {
    "fields": [
        {
            "key": "about",
            "label": "About the study",
            "type": "section",
            "help": "Read the methods.",
        },
        {
            "key": "design",
            "label": "Study design",
            "type": "select",
            "required": True,
            "options": ["RCT", "Cohort"],
        },
        {"key": "country", "label": "Country", "type": "short_text"},
        {"key": "notes", "label": "Notes", "type": "long_text"},
        {
            "key": "n",
            "label": "Participants",
            "type": "number",
            "unit": "people",
            "integer": True,
            "minimum": 1,
            "maximum": 100000,
        },
        {"key": "dose", "label": "Dose", "type": "number", "unit": "mg", "minimum": 0.5},
        {
            "key": "outcomes_measured",
            "label": "Outcomes",
            "type": "multi_select",
            "options": ["Sleep", "Fatigue", "Errors"],
        },
        {"key": "blinded", "label": "Assessors blinded", "type": "yes_no_unclear"},
        {"key": "published", "label": "Published on", "type": "date"},
        {
            "key": "arms",
            "label": "Arms",
            "type": "table",
            "min_rows": 2,
            "max_rows": 4,
            "columns": [
                {"key": "arm", "label": "Arm", "type": "short_text", "required": True},
                {"key": "n", "label": "N", "type": "number", "integer": True},
                {"key": "mean", "label": "Mean", "type": "number", "unit": "hours"},
            ],
        },
    ]
}
SCHEMA = parse_schema(TRIAL)

ENTRY: dict[str, Any] = {
    "design": "RCT",
    "country": "  Norway ",
    "notes": "",
    "n": "1,204",
    "dose": 2.5,
    "outcomes_measured": ["Errors", "Sleep"],
    "blinded": "unclear",
    "published": "2016-03-01",
    "arms": [
        {"arm": "Melatonin", "n": 602, "mean": 6.5},
        {"arm": "Placebo", "n": "602", "mean": "6"},
        {},
    ],
}


def test_a_schema_round_trips_unchanged() -> None:
    stored = schema_to_json(SCHEMA)
    assert parse_schema(stored) == SCHEMA
    assert stored["fields"][4] == {
        "key": "n",
        "label": "Participants",
        "type": "number",
        "unit": "people",
        "integer": True,
        "minimum": 1,
        "maximum": 100000,
    }
    assert stored["fields"][5]["minimum"] == 0.5
    assert stored["fields"][9]["min_rows"] == 2
    assert next(field.key for field in SCHEMA.values()) == "design"  # sections hold nothing


@pytest.mark.parametrize(
    ("raw", "problem"),
    [
        ([], 'A form is an object with a list of "fields".'),
        ({"fields": [], "extra": 1}, "settings Winnow does not know"),
        ({"fields": [1]}, "Field 1 is not a field."),
        (
            {"fields": [{"key": "Bad Key", "label": "x", "type": "short_text"}]},
            "the key must start",
        ),
        ({"fields": [{"key": "a", "label": " ", "type": "short_text"}]}, "Field 1 needs a label."),
        ({"fields": [{"key": "a", "label": "x" * 301, "type": "short_text"}]}, "at most 300"),
        ({"fields": [{"key": "a", "label": "A", "type": "slider"}]}, "no type Winnow knows"),
        (
            {"fields": [{"key": "a", "label": "A", "type": "short_text", "colour": "red"}]},
            "does not know: ['colour']",
        ),
        (
            {"fields": [{"key": "a", "label": "A", "type": "short_text", "help": "x" * 2001}]},
            "help text",
        ),
        (
            {"fields": [{"key": "a", "label": "A", "type": "short_text", "required": "yes"}]},
            "required is true or false",
        ),
        ({"fields": [{"key": "a", "label": "A", "type": "select"}]}, "needs at least one option"),
        (
            {"fields": [{"key": "a", "label": "A", "type": "select", "options": ["x", "x"]}]},
            "lists an option twice",
        ),
        (
            {"fields": [{"key": "a", "label": "A", "type": "select", "options": ["x", " "]}]},
            "an empty option",
        ),
        (
            {
                "fields": [
                    {
                        "key": "a",
                        "label": "A",
                        "type": "select",
                        "options": [str(i) for i in range(101)],
                    }
                ]
            },
            "at most 100 options",
        ),
        (
            {"fields": [{"key": "a", "label": "A", "type": "select", "options": ["x" * 201]}]},
            "an option has at most",
        ),
        (
            {"fields": [{"key": "a", "label": "A", "type": "select", "options": "x"}]},
            "options are a list",
        ),
        (
            {"fields": [{"key": "a", "label": "A", "type": "short_text", "options": ["x"]}]},
            "only select fields",
        ),
        (
            {"fields": [{"key": "a", "label": "A", "type": "short_text", "unit": "kg"}]},
            "only numbers have a unit",
        ),
        (
            {"fields": [{"key": "a", "label": "A", "type": "short_text", "integer": True}]},
            "only numbers can be whole",
        ),
        (
            {"fields": [{"key": "a", "label": "A", "type": "date", "minimum": 1}]},
            "only numbers have a minimum",
        ),
        (
            {"fields": [{"key": "a", "label": "A", "type": "number", "maximum": "ten"}]},
            "the maximum must be a number",
        ),
        (
            {"fields": [{"key": "a", "label": "A", "type": "number", "minimum": 5, "maximum": 1}]},
            "minimum is above",
        ),
        ({"fields": [{"key": "a", "label": "A", "type": "table"}]}, "at least one column"),
        (
            {
                "fields": [
                    {
                        "key": "a",
                        "label": "A",
                        "type": "table",
                        "columns": [{"key": "b", "label": "B", "type": "table"}],
                    }
                ]
            },
            "a table column cannot be a table",
        ),
        (
            {
                "fields": [
                    {
                        "key": "a",
                        "label": "A",
                        "type": "table",
                        "columns": [{"key": "b", "label": "B", "type": "date"}] * 2,
                    }
                ]
            },
            "Two columns of 'A' have the key 'b'",
        ),
        (
            {
                "fields": [
                    {
                        "key": "a",
                        "label": "A",
                        "type": "table",
                        "columns": [
                            {"key": f"c{i}", "label": "C", "type": "date"} for i in range(31)
                        ],
                    }
                ]
            },
            "at most 30 columns",
        ),
        (
            {
                "fields": [
                    {
                        "key": "a",
                        "label": "A",
                        "type": "table",
                        "columns": [{"key": "b", "label": "B", "type": "date"}],
                        "min_rows": -1,
                    }
                ]
            },
            "fewest rows",
        ),
        (
            {
                "fields": [
                    {
                        "key": "a",
                        "label": "A",
                        "type": "table",
                        "columns": [{"key": "b", "label": "B", "type": "date"}],
                        "min_rows": 3,
                        "max_rows": 2,
                    }
                ]
            },
            "most rows is a whole number from 3",
        ),
        (
            {"fields": [{"key": "a", "label": "A", "type": "short_text", "max_rows": 2}]},
            "only tables have columns",
        ),
        (
            {
                "fields": [
                    {"key": "a", "label": "A", "type": "date"},
                    {"key": "a", "label": "B", "type": "date"},
                ]
            },
            "Two fields have the key 'a'",
        ),
        (
            {"fields": [{"key": f"f{i}", "label": "F", "type": "date"} for i in range(201)]},
            "at most 200 fields",
        ),
    ],
)
def test_a_broken_schema_lists_its_problems(raw: object, problem: str) -> None:
    with pytest.raises(SchemaError) as error:
        parse_schema(raw)
    assert any(problem in text for text in error.value.problems), error.value.problems


def test_every_problem_is_listed_at_once() -> None:
    with pytest.raises(SchemaError) as error:
        parse_schema(
            {
                "fields": [
                    {"key": "A", "label": "", "type": "x"},
                    {"key": "b", "label": "B", "type": "select"},
                ]
            }
        )
    assert len(error.value.problems) == 4


def test_an_entry_is_normalised() -> None:
    assert validate_entry(SCHEMA, ENTRY, complete=True) == {
        "design": "RCT",
        "country": "Norway",
        "n": 1204,
        "dose": 2.5,
        "outcomes_measured": ["Sleep", "Errors"],  # in the form's order
        "blinded": "unclear",
        "published": "2016-03-01",
        "arms": [
            {"arm": "Melatonin", "n": 602, "mean": 6.5},
            {"arm": "Placebo", "n": 602, "mean": 6},
        ],
    }


def test_a_draft_may_be_partial_but_a_submission_may_not() -> None:
    assert validate_entry(SCHEMA, {"country": "Norway"}, complete=False) == {"country": "Norway"}
    with pytest.raises(EntryError) as error:
        validate_entry(SCHEMA, {"arms": [{"n": 3}]}, complete=True)
    assert error.value.problems == {
        "design": "Required.",
        "arms[1].arm": "Required.",
        "arms": "At least 2 rows.",
    }


@pytest.mark.parametrize(
    ("data", "path", "problem"),
    [
        ([], "", "An entry is an object"),
        ({"weight": 1}, "weight", "no such field"),
        ({"country": 5}, "country", "Should be text."),
        ({"country": "x" * 501}, "country", "At most 500 characters."),
        ({"notes": "x" * 20_001}, "notes", "At most 20,000 characters."),
        ({"n": "many"}, "n", "Should be a number."),
        ({"n": True}, "n", "Should be a number."),
        ({"n": [1]}, "n", "Should be a number."),
        ({"n": float("inf")}, "n", "Should be a number."),
        ({"n": 2.5}, "n", "Should be a whole number."),
        ({"n": 0}, "n", "At least 1."),
        ({"n": 100001}, "n", "At most 100000."),
        ({"dose": 0.1}, "dose", "At least 0.5."),
        ({"design": "Case report"}, "design", "Choose one of the options."),
        ({"outcomes_measured": "Sleep"}, "outcomes_measured", "a list of options"),
        ({"outcomes_measured": ["Mood"]}, "outcomes_measured", "Choose from the options."),
        ({"outcomes_measured": ["Sleep", "Sleep"]}, "outcomes_measured", "chosen twice"),
        ({"blinded": "maybe"}, "blinded", "Yes, no or unclear."),
        ({"published": "2016-02-30"}, "published", "a real date"),
        ({"published": "1/3/2016"}, "published", "a real date"),
        ({"published": 20160301}, "published", "Should be a date."),
        ({"arms": {"arm": "A"}}, "arms", "A table is a list of rows."),
        ({"arms": ["A"]}, "arms[1]", "A row is an object"),
        ({"arms": [{"dose": 1}]}, "arms[1].dose", "no such column"),
        ({"arms": [{"arm": str(i)} for i in range(5)]}, "arms", "At most 4 rows."),
    ],
)
def test_a_wrong_value_is_named_by_its_field(data: object, path: str, problem: str) -> None:
    with pytest.raises(EntryError) as error:
        validate_entry(SCHEMA, data, complete=False)
    assert problem in error.value.problems[path]


def test_empty_values_are_absent() -> None:
    empty: dict[str, object] = {
        "design": "",
        "country": "  ",
        "n": "",
        "outcomes_measured": [],
        "blinded": "",
        "published": "",
        "arms": None,
    }
    assert validate_entry(SCHEMA, empty, complete=False) == {}


def test_a_required_table_needs_a_row_even_without_a_fewest() -> None:
    schema = parse_schema(
        {
            "fields": [
                {
                    "key": "t",
                    "label": "T",
                    "type": "table",
                    "required": True,
                    "columns": [{"key": "a", "label": "A", "type": "date"}],
                }
            ]
        }
    )
    with pytest.raises(EntryError) as error:
        validate_entry(schema, {}, complete=True)
    assert error.value.problems == {"t": "At least 1 row."}


def test_differences_are_field_by_field_and_cell_by_cell() -> None:
    a = validate_entry(SCHEMA, ENTRY, complete=True)
    b = validate_entry(
        SCHEMA,
        {
            **ENTRY,
            "country": "Norway",
            "n": 1200,
            "arms": [
                *ENTRY["arms"][:1],
                {"arm": "Placebo", "n": 601, "mean": 6},
                {"arm": "Usual care"},
            ],
        },
        complete=True,
    )
    found = differences(SCHEMA, a, b)
    assert [(d.path, d.label, d.a, d.b) for d in found] == [
        ("n", "Participants", 1204, 1200),
        ("arms[2].n", "Arms, row 2: N", 602, 601),
        ("arms[3].arm", "Arms, row 3: Arm", None, "Usual care"),
    ]
    assert differences(SCHEMA, {}, {}) == []


def test_long_and_wide_layouts_for_a_two_arm_trial() -> None:
    first = validate_entry(SCHEMA, ENTRY, complete=True)
    second = validate_entry(
        SCHEMA,
        {"design": "Cohort", "arms": [{"arm": "All"}, {"arm": "None"}, {"arm": "Some", "n": 3}]},
        complete=True,
    )
    entries = [
        EntryForExport("r1", "Okafor 2016", "Ngozi Okafor", first),
        EntryForExport("r2", "Lindqvist 2017", "consensus", second),
    ]
    long = long_rows(SCHEMA, entries)
    assert set(long[0]) == set(LONG_COLUMNS)
    assert long[0] == {
        "record_id": "r1",
        "study": "Okafor 2016",
        "extractor": "Ngozi Okafor",
        "field": "design",
        "label": "Study design",
        "row": "",
        "column": "",
        "value": "RCT",
        "unit": "",
    }
    assert {"field": "outcomes_measured", "value": "Sleep; Errors"}.items() <= long[4].items()
    assert {
        "field": "arms",
        "row": 2,
        "column": "mean",
        "value": 6,
        "unit": "hours",
        "label": "Arms: Mean",
    }.items() <= long[12].items()
    assert len(long) == 13 + 5  # 13 values in the first entry; design and four cells in the second

    wide = wide_rows(SCHEMA, entries)
    assert wide.headers[:4] == ["record_id", "study", "extractor", "design"]
    assert wide.headers[-3:] == ["arms[3].arm", "arms[3].n", "arms[3].mean"]
    assert wide.rows[0]["outcomes_measured"] == "Sleep; Errors"
    assert wide.rows[0]["arms[2].mean"] == 6
    assert wide.rows[0]["arms[3].arm"] == ""
    assert wide.rows[1]["arms[3].n"] == 3
    assert wide.rows[1]["country"] == ""
    assert wide_rows(SCHEMA, []).headers[-1] == "published"  # no table rows when no data
