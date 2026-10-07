"""What each polars format keeps, as the plugin's documentation states it."""

import polars as pl
import pytest

from ditto import recorders


def _round_trip(name: str, frame: pl.DataFrame) -> pl.DataFrame:
    recorder = recorders.get(name)
    return recorder.loads(recorder.dumps(frame))


NARROW_TYPES = [
    pytest.param(pl.Series("c", [1.5], dtype=pl.Float32), pl.Float64, id="float32"),
    pytest.param(pl.Series("c", [1], dtype=pl.Int8), pl.Int64, id="int8"),
]


@pytest.mark.parametrize("name", ["polars.parquet", "polars.ipc"])
@pytest.mark.parametrize(
    "column",
    [
        pl.Series("c", [1.5], dtype=pl.Float32),
        pl.Series("c", [1], dtype=pl.Int8),
        pl.Series("c", ["001"]),
    ],
    ids=["float32", "int8", "number-like-string"],
)
def test_binary_formats_keep_a_column_type(name: str, column: pl.Series) -> None:
    """Parquet and IPC load back each column with its type and values."""
    frame = column.to_frame()

    actual = _round_trip(name, frame)

    assert actual.equals(frame)
    assert actual.schema == frame.schema


@pytest.mark.parametrize("name", ["polars.csv", "polars.ndjson"])
@pytest.mark.parametrize(("column", "expected"), NARROW_TYPES)
def test_text_formats_widen_a_narrow_type(
    name: str, column: pl.Series, expected: pl.DataType
) -> None:
    """CSV and NDJSON infer types again on load, widening narrow ones."""
    actual = _round_trip(name, column.to_frame()).schema["c"]

    assert actual == expected


def test_csv_reads_a_number_like_string_back_as_a_number() -> None:
    """CSV loads the string "001" back as the integer 1."""
    frame = pl.DataFrame({"code": ["001"]})

    actual = _round_trip("polars.csv", frame)["code"].to_list()

    expected = [1]
    assert actual == expected


def test_ndjson_keeps_a_number_like_string() -> None:
    """NDJSON loads the string "001" back as a string, since JSON quotes it."""
    frame = pl.DataFrame({"code": ["001"]})

    actual = _round_trip("polars.ndjson", frame)

    assert actual.equals(frame)
