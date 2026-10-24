# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading sheet rows by docs/sheet-format.md."""

from __future__ import annotations

import pytest

from squarepot_server.api.models import FieldSchema
from squarepot_server.config import DEFAULT_SCHEMA_FILE
from squarepot_server.fields import (
    MAX_CUSTOM_COLUMNS,
    MAX_CUSTOM_NAME,
    MAX_CUSTOM_VALUE,
    Cell,
    Issue,
    TabError,
    column_name,
    load_schema,
    parse_tab,
)


@pytest.fixture(scope="module")
def schema() -> FieldSchema:
    return load_schema(DEFAULT_SCHEMA_FILE)


def one(schema: FieldSchema, header: list[Cell], row: list[Cell]) -> dict[str, str]:
    parsed = parse_tab(schema, [header, row])
    assert parsed.issues == []
    [result] = parsed.rows
    return result.fields


def test_headers_match_keys_and_aliases_ignoring_case(schema: FieldSchema) -> None:
    parsed = parse_tab(
        schema,
        [
            [" UID ", "Genus", "Cultivated_Variety", "information", "My own column"],
            ["4217", "Echeveria", "Perle von Nürnberg", "gift", "ignored"],
        ],
    )
    [row] = parsed.rows
    assert row.tag == "004217"
    assert row.fields == {"genus": "Echeveria", "cultivar": "Perle von Nürnberg", "notes": "gift"}
    assert row.custom == {"My own column": "ignored"}


def test_unknown_columns_are_custom_columns_read_as_text(schema: FieldSchema) -> None:
    parsed = parse_tab(
        schema,
        [
            ["genus", "  Marathon ", "", "pot  width", "soil", 2024, "Bought"],
            ["Lithops", " yes ", "lost", 7.0, "", 12.5, True],
            ["Conophytum"],
        ],
    )
    assert parsed.issues == []
    assert parsed.custom_columns == ["Marathon", "pot width", "soil", "2024", "Bought"]
    first, second = parsed.rows
    assert first.fields == {"genus": "Lithops"}
    assert first.custom == {"Marathon": "yes", "pot width": "7", "2024": "12.5", "Bought": "TRUE"}
    assert second.custom == {}


def test_custom_columns_with_the_same_name_are_left_out(schema: FieldSchema) -> None:
    parsed = parse_tab(
        schema, [["genus", "Soil", "mark", "soil "], ["Lithops", "pumice", "x", "grit"]]
    )
    assert parsed.custom_columns == ["mark"]
    assert parsed.rows[0].custom == {"mark": "x"}
    assert parsed.issues == [
        Issue(1, "B", "columns B and D have the same name 'Soil': they are left out")
    ]


def test_custom_columns_over_the_limits_are_left_out(schema: FieldSchema) -> None:
    long_name = "n" * (MAX_CUSTOM_NAME + 1)
    header: list[Cell] = ["genus", long_name, *(f"c{i}" for i in range(MAX_CUSTOM_COLUMNS + 1))]
    parsed = parse_tab(schema, [header, ["Lithops"]])
    assert parsed.custom_columns == [f"c{i}" for i in range(MAX_CUSTOM_COLUMNS)]
    assert [(issue.row, issue.column) for issue in parsed.issues] == [
        (1, "B"),
        (1, column_name(len(header) - 1)),
    ]
    assert "longer than 64 characters" in parsed.issues[0].message
    assert "more than 50 custom columns" in parsed.issues[1].message


def test_a_long_custom_value_is_cut_short(schema: FieldSchema) -> None:
    parsed = parse_tab(schema, [["genus", "story"], ["Lithops", "x" * 5000]])
    value = parsed.rows[0].custom["story"]
    assert len(value) == MAX_CUSTOM_VALUE
    assert value.endswith("…")
    assert parsed.issues == [Issue(2, "B", "longer than 1000 characters: cut short")]


def test_description_is_a_field_of_its_own_beside_notes(schema: FieldSchema) -> None:
    assert one(
        schema, ["genus", "information", "Description"], ["Lithops", "gift", "from seed"]
    ) == {"genus": "Lithops", "notes": "gift", "description": "from seed"}


def test_every_imported_key_comes_from_the_schema(schema: FieldSchema) -> None:
    keys = [field.key for field in schema.fields]
    values: list[Cell] = ["x"] * len(keys)
    values[keys.index("tag")] = 4217
    for key in ("seeding_date", "purchase_date"):
        values[keys.index(key)] = "2024-03-15"
    values[keys.index("price")] = 12.5
    values[keys.index("currency")] = "eur"
    values[keys.index("label_type")] = "h"
    parsed = parse_tab(schema, [list(keys), values])
    assert parsed.issues == []
    [row] = parsed.rows
    assert set(row.fields) == set(keys) - {"tag"}


@pytest.mark.parametrize(
    ("header", "message"),
    [
        (["tag", "species"], "no 'genus' column"),
        (["genus", "tag", "uid"], "columns B and C both hold 'tag'"),
    ],
)
def test_tab_level_problems_stop_the_import(
    schema: FieldSchema, header: list[Cell], message: str
) -> None:
    with pytest.raises(TabError, match=message):
        parse_tab(schema, [header, ["Lithops"]])


def test_an_empty_tab_is_rejected(schema: FieldSchema) -> None:
    with pytest.raises(TabError):
        parse_tab(schema, [])


@pytest.mark.parametrize(
    ("cell", "tag"),
    [(4217, "004217"), (4217.0, "004217"), ("4217", "004217"), (" 004217 ", "004217")],
)
def test_tags_are_padded_to_six_digits(schema: FieldSchema, cell: Cell, tag: str) -> None:
    [row] = parse_tab(schema, [["tag", "genus"], [cell, "Lithops"]]).rows
    assert row.tag == tag


@pytest.mark.parametrize("cell", ["12a", "1234567", 0, "000000", 42.5, True])
def test_invalid_tags_are_reported_and_the_row_is_kept(schema: FieldSchema, cell: Cell) -> None:
    parsed = parse_tab(schema, [["genus", "tag"], ["Lithops", cell]])
    [row] = parsed.rows
    assert row.tag is None
    assert [(issue.row, issue.column) for issue in parsed.issues] == [(2, "B")]


@pytest.mark.parametrize(
    ("cell", "value"),
    [
        (45366, "2024-03-15"),
        ("2024-03-15", "2024-03-15"),
        ("15.03.2024", "2024-03-15"),
        ("5.3.2024", "2024-03-05"),
    ],
)
def test_dates(schema: FieldSchema, cell: Cell, value: str) -> None:
    assert one(schema, ["genus", "seeding_date"], ["Lithops", cell]) == {
        "genus": "Lithops",
        "seeding_date": value,
    }


@pytest.mark.parametrize(
    "cell", ["March 2024", "2024-02-30", "15/03/2024", "2024-3-5", 20240315, 1e300, float("nan")]
)
def test_invalid_dates_are_dropped_and_reported(schema: FieldSchema, cell: Cell) -> None:
    parsed = parse_tab(schema, [["genus", "seeding_date"], ["Lithops", cell]])
    assert parsed.rows[0].fields == {"genus": "Lithops"}
    assert parsed.issues == [Issue(2, "B", "not a date (YYYY-MM-DD)")]


@pytest.mark.parametrize(
    ("cell", "value"), [(12.5, "12.5"), (12, "12"), ("12.50", "12.50"), (0.1, "0.1")]
)
def test_decimals_are_exact_strings(schema: FieldSchema, cell: Cell, value: str) -> None:
    assert one(schema, ["genus", "price"], ["Lithops", cell])["price"] == value


@pytest.mark.parametrize("cell", ["cheap", "NaN", "Infinity"])
def test_invalid_decimals_are_reported(schema: FieldSchema, cell: Cell) -> None:
    parsed = parse_tab(schema, [["genus", "price"], ["Lithops", cell]])
    assert parsed.rows[0].fields == {"genus": "Lithops"}
    assert len(parsed.issues) == 1


def test_currency_is_upper_case(schema: FieldSchema) -> None:
    assert one(schema, ["genus", "currency"], ["Lithops", " eur "])["currency"] == "EUR"


def test_an_invalid_currency_is_reported(schema: FieldSchema) -> None:
    parsed = parse_tab(schema, [["genus", "currency"], ["Lithops", "euro"]])
    assert parsed.rows[0].fields == {"genus": "Lithops"}
    assert [issue.column for issue in parsed.issues] == ["B"]


@pytest.mark.parametrize(("cell", "label_type"), [("h", "h"), (" H ", "h"), ("V", "v")])
def test_the_label_type_is_lower_case(schema: FieldSchema, cell: str, label_type: str) -> None:
    assert one(schema, ["genus", "label_type"], ["Lithops", cell])["label_type"] == label_type


def test_an_unknown_label_type_is_reported(schema: FieldSchema) -> None:
    parsed = parse_tab(schema, [["genus", "label_type"], ["Lithops", "horizontal"]])
    assert parsed.rows[0].fields == {"genus": "Lithops"}
    assert [issue.column for issue in parsed.issues] == ["B"]


def test_number_cells_in_text_fields_read_as_text(schema: FieldSchema) -> None:
    fields = one(schema, ["genus", "field_number"], ["Lithops", 1234.0])
    assert fields["field_number"] == "1234"


def test_rows_without_genus_are_skipped_but_keep_their_number(schema: FieldSchema) -> None:
    parsed = parse_tab(
        schema,
        [
            ["tag", "genus", "species"],
            [4217, "", "lesliei"],
            [],
            ["", " ", None],
            [4218, "Lithops"],
        ],
    )
    assert [row.tag for row in parsed.rows] == ["004218"]
    assert parsed.skipped_tags == ["004217"]
    assert parsed.issues == [Issue(2, "", "skipped: no valid genus")]


def test_short_rows_are_padded_with_empty_cells(schema: FieldSchema) -> None:
    parsed = parse_tab(schema, [["genus", "species", "notes"], ["Lithops"]])
    assert parsed.rows[0].fields == {"genus": "Lithops"}


@pytest.mark.parametrize(("index", "name"), [(0, "A"), (25, "Z"), (26, "AA"), (701, "ZZ")])
def test_column_names(index: int, name: str) -> None:
    assert column_name(index) == name
