"""What each pyarrow format keeps, as the plugin's documentation states it."""

import datetime
import decimal

import pyarrow as pa
import pytest

from ditto import recorders


def _round_trip(name: str, table: pa.Table) -> pa.Table:
    recorder = recorders.get(name)
    return recorder.loads(recorder.dumps(table))


TIME32_S = pa.array([datetime.time(1, 2, 3)], pa.time32("s"))
TIMESTAMP_S = pa.array([1], pa.timestamp("s"))
DATE64 = pa.array([datetime.date(2024, 1, 1)], pa.date64())


@pytest.mark.parametrize(
    "column",
    [TIME32_S, TIMESTAMP_S, DATE64],
    ids=["time32-s", "timestamp-s", "date64"],
)
def test_feather_keeps_a_type_parquet_coerces(column: pa.Array) -> None:
    """Feather loads back a column type that parquet has no exact equivalent for."""
    table = pa.table({"c": column})

    actual = _round_trip("pyarrow.feather", table)

    assert actual.equals(table)


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        (TIME32_S, pa.time32("ms")),
        (TIMESTAMP_S, pa.timestamp("ms")),
        (DATE64, pa.date32()),
    ],
    ids=["time32-s", "timestamp-s", "date64"],
)
def test_parquet_coerces_a_type_it_has_no_exact_equivalent_for(
    column: pa.Array, expected: pa.DataType
) -> None:
    """Parquet loads second-resolution times as milliseconds and date64 as date32."""
    actual = (
        _round_trip("pyarrow.parquet", pa.table({"c": column})).schema.field(0).type
    )

    assert actual == expected


@pytest.mark.parametrize("name", ["pyarrow.parquet", "pyarrow.feather"])
def test_binary_formats_keep_schema_metadata(name: str) -> None:
    """Parquet and feather load back a table's schema metadata."""
    table = pa.table({"a": [1]}).replace_schema_metadata({b"source": b"test"})

    actual = _round_trip(name, table).schema.metadata

    expected = {b"source": b"test"}
    assert actual == expected


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        pytest.param(pa.array([1], pa.int8()), pa.int64(), id="int8"),
        pytest.param(pa.array([1.5], pa.float32()), pa.float64(), id="float32"),
        pytest.param(
            pa.array([decimal.Decimal("1.10")], pa.decimal128(5, 2)),
            pa.float64(),
            id="decimal128",
        ),
        pytest.param(
            pa.array(["a"], pa.large_string()), pa.string(), id="large_string"
        ),
    ],
)
def test_csv_widens_a_narrow_or_specialised_type(
    column: pa.Array, expected: pa.DataType
) -> None:
    """CSV infers types again on load, widening narrow and specialised ones."""
    actual = _round_trip("pyarrow.csv", pa.table({"c": column})).schema.field(0).type

    assert actual == expected


def test_csv_reads_a_number_like_string_back_as_a_number() -> None:
    """CSV loads the string "001" back as the integer 1."""
    table = pa.table({"code": ["001"]})

    actual = _round_trip("pyarrow.csv", table).column("code").to_pylist()

    expected = [1]
    assert actual == expected


def test_csv_reads_a_null_string_back_as_an_empty_string() -> None:
    """CSV loads a null in a string column back as an empty string."""
    table = pa.table({"n": [1, 2], "s": ["x", None]})

    actual = _round_trip("pyarrow.csv", table).column("s").to_pylist()

    expected = ["x", ""]
    assert actual == expected


def test_csv_cannot_write_a_list_column() -> None:
    """CSV raises rather than writing a list column."""
    table = pa.table({"c": [[1], [2, 3]]})

    with pytest.raises(pa.ArrowInvalid):
        recorders.get("pyarrow.csv").dumps(table)


@pytest.mark.xfail(
    strict=True,
    reason="CSV writes the null row as a blank line, which isn't read back (#247)",
)
def test_csv_keeps_a_null_row_in_a_single_column_table() -> None:
    """CSV loads back every row of a single-column table that has a null."""
    table = pa.table({"a": [1, None, 3]})

    actual = _round_trip("pyarrow.csv", table).num_rows

    expected = 3
    assert actual == expected
