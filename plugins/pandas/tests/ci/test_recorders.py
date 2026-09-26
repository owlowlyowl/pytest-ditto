from pathlib import Path

import pandas as pd

from ditto_pandas.recorders import pandas_csv, pandas_json, pandas_parquet


def _sample_dataframe() -> pd.DataFrame:
    return pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})


def test_parquet_round_trip_preserves_dataframe_values(tmp_path: Path) -> None:
    """Parquet save and load produces a DataFrame equal to the original."""
    df = _sample_dataframe()
    filepath = tmp_path / "snapshot.pandas.parquet"

    pandas_parquet.save(df, filepath)
    actual = pandas_parquet.load(filepath)

    pd.testing.assert_frame_equal(actual, df)


def test_json_round_trip_preserves_dataframe_values(tmp_path: Path) -> None:
    """JSON save and load produces a DataFrame equal to the original."""
    df = _sample_dataframe()
    filepath = tmp_path / "snapshot.pandas.json"

    pandas_json.save(df, filepath)
    actual = pandas_json.load(filepath)

    pd.testing.assert_frame_equal(actual, df)


def test_csv_round_trip_preserves_dataframe_values(tmp_path: Path) -> None:
    """CSV save and load produces a DataFrame equal to the original for simple indices.

    check_index_type=False because CSV has no type metadata: a RangeIndex is written
    as plain integers and read back as an Int64 index. Only single-level numeric or
    string indices round-trip reliably — DatetimeIndex, PeriodIndex, CategoricalIndex,
    and MultiIndex are not supported.
    """
    df = _sample_dataframe()
    filepath = tmp_path / "snapshot.pandas.csv"

    pandas_csv.save(df, filepath)
    actual = pandas_csv.load(filepath)

    pd.testing.assert_frame_equal(actual, df, check_index_type=False)


def test_parquet_recorder_extension_is_correct() -> None:
    """Parquet recorder uses the pandas.parquet compound extension."""
    assert pandas_parquet.extension == "pandas.parquet"


def test_json_recorder_extension_is_correct() -> None:
    """JSON recorder uses the pandas.json compound extension."""
    assert pandas_json.extension == "pandas.json"


def test_csv_recorder_extension_is_correct() -> None:
    """CSV recorder uses the pandas.csv compound extension."""
    assert pandas_csv.extension == "pandas.csv"
