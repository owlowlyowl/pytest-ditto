"""The pandas recorders, as registered through the 2.0 plugin contract."""

from pathlib import Path

import pandas as pd
import pytest

import ditto
from ditto import recorders

NAMES = ["pandas.parquet", "pandas.json", "pandas.csv"]


def _sample_dataframe() -> pd.DataFrame:
    return pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})


@pytest.mark.parametrize("name", NAMES)
def test_registers_each_recorder_under_its_dotted_name(name: str) -> None:
    """Each recorder is discoverable by its `pandas.<format>` name."""
    assert name in recorders.RECORDER_REGISTRY


def test_registrations_keep_the_plugin_contract() -> None:
    """No contract problem involves a pandas recorder."""
    affected = {n for p in recorders.RECORDER_REGISTRY.problems for n in p.names}

    assert affected.isdisjoint(NAMES)


@pytest.mark.parametrize("name", NAMES)
def test_derives_a_namespaced_mark_for_each_recorder(name: str) -> None:
    """`ditto.pandas.<format>` is the mark for `record("pandas.<format>")`."""
    fmt = name.removeprefix("pandas.")

    actual = getattr(ditto.pandas, fmt)

    expected = pytest.mark.record(name)
    assert actual == expected


@ditto.pandas.parquet
def test_parquet_mark_selects_the_parquet_recorder(snapshot) -> None:
    """The parquet mark gives the snapshot fixture the parquet recorder, named
    `pandas.parquet` in snapshot filenames."""
    actual = snapshot.recorder

    assert actual is recorders.get("pandas.parquet")
    assert snapshot.recorder_name == "pandas.parquet"


@pytest.mark.parametrize("name", ["pandas.parquet", "pandas.json"])
def test_round_trips_a_dataframe(tmp_path: Path, name: str) -> None:
    """Parquet and JSON load back exactly the DataFrame they saved."""
    df = _sample_dataframe()
    recorder = recorders.get(name)
    filepath = tmp_path / f"snapshot.{name}"

    recorder.save(df, filepath)
    actual = recorder.load(filepath)

    pd.testing.assert_frame_equal(actual, df)


def test_csv_round_trips_a_dataframe_except_for_the_index_type(
    tmp_path: Path,
) -> None:
    """CSV loads back the saved values, with the RangeIndex read back as Int64.

    check_index_type=False because CSV has no type metadata: a RangeIndex is written
    as plain integers and read back as an Int64 index. Only single-level numeric or
    string indices round-trip reliably — DatetimeIndex, PeriodIndex, CategoricalIndex,
    and MultiIndex are not supported.
    """
    df = _sample_dataframe()
    filepath = tmp_path / "snapshot.pandas.csv"

    recorders.get("pandas.csv").save(df, filepath)
    actual = recorders.get("pandas.csv").load(filepath)

    pd.testing.assert_frame_equal(actual, df, check_index_type=False)


def test_csv_reads_the_index_back_as_the_index(tmp_path: Path) -> None:
    """The saved index is restored as the index, not as a data column (#40)."""
    df = _sample_dataframe()
    filepath = tmp_path / "snapshot.pandas.csv"

    recorders.get("pandas.csv").save(df, filepath)
    actual = recorders.get("pandas.csv").load(filepath)

    assert list(actual.columns) == ["a", "b"]


def test_csv_round_trips_a_string_index_exactly(tmp_path: Path) -> None:
    """A named string index survives a CSV round trip unchanged."""
    df = _sample_dataframe().set_index(pd.Index(["x", "y", "z"], name="key"))
    filepath = tmp_path / "snapshot.pandas.csv"

    recorders.get("pandas.csv").save(df, filepath)
    actual = recorders.get("pandas.csv").load(filepath)

    pd.testing.assert_frame_equal(actual, df)
