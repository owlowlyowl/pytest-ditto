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
def test_round_trips_a_dataframe(name: str) -> None:
    """Parquet and JSON load back exactly the DataFrame they saved."""
    df = _sample_dataframe()
    recorder = recorders.get(name)
    actual = recorder.loads(recorder.dumps(df))

    pd.testing.assert_frame_equal(actual, df)


def test_csv_round_trips_a_dataframe_except_for_the_index_type() -> None:
    """CSV loads back the saved values, with the RangeIndex read back as Int64.

    check_index_type=False because CSV has no type metadata: a RangeIndex is written
    as plain integers and read back as an Int64 index. Only single-level numeric or
    string indices round-trip reliably — DatetimeIndex, PeriodIndex, CategoricalIndex,
    and MultiIndex are not supported.
    """
    df = _sample_dataframe()
    recorder = recorders.get("pandas.csv")

    actual = recorder.loads(recorder.dumps(df))

    pd.testing.assert_frame_equal(actual, df, check_index_type=False)


def test_csv_ends_lines_with_newlines_on_every_platform() -> None:
    """CSV bytes don't depend on the platform's line separator."""
    actual = recorders.get("pandas.csv").dumps(_sample_dataframe())

    assert b"\n" in actual
    assert b"\r" not in actual


def test_csv_reads_the_index_back_as_the_index() -> None:
    """The saved index is restored as the index, not as a data column (#40)."""
    df = _sample_dataframe()
    recorder = recorders.get("pandas.csv")

    actual = recorder.loads(recorder.dumps(df))

    assert list(actual.columns) == ["a", "b"]


def test_csv_round_trips_a_string_index_exactly() -> None:
    """A named string index survives a CSV round trip unchanged."""
    df = _sample_dataframe().set_index(pd.Index(["x", "y", "z"], name="key"))
    recorder = recorders.get("pandas.csv")

    actual = recorder.loads(recorder.dumps(df))

    pd.testing.assert_frame_equal(actual, df)


# ── Committed snapshots ───────────────────────────────────────────────────────

SNAPSHOTS = Path(__file__).parent / ".ditto"


def _recorder_name(path: Path) -> str:
    """The recorder name that ends a snapshot filename, e.g. `pandas.csv`."""
    return path.name.rpartition("@")[2].partition(".")[2]


@pytest.mark.parametrize(
    "path",
    [
        p
        for p in sorted(SNAPSHOTS.iterdir())
        if _recorder_name(p) in {"pandas.csv", "pandas.json"}
    ],
    ids=lambda p: p.name,
)
def test_rewriting_a_committed_text_snapshot_reproduces_its_bytes(path: Path) -> None:
    """Loading a committed snapshot and dumping it again gives the same bytes."""
    recorder = recorders.get(_recorder_name(path))
    raw = path.read_bytes()

    actual = recorder.dumps(recorder.loads(raw))

    assert actual == raw
