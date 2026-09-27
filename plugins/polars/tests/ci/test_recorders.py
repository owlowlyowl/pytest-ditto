"""The polars recorders, as registered through the 2.0 plugin contract."""

from datetime import datetime

from pathlib import Path

import polars as pl
import polars.testing  # noqa: F401
import pytest

import ditto
from ditto import recorders

NAMES = ["polars.parquet", "polars.ipc", "polars.csv", "polars.ndjson"]


def _sample_dataframe() -> pl.DataFrame:
    return pl.DataFrame({
        "a": [1, 2, 3],
        "b": [4.0, 5.0, 6.0],
        "c": ["x", "y", "z"],
    })


def _rich_dataframe() -> pl.DataFrame:
    return pl.DataFrame({
        "ints": [1, None, 3],
        "floats": [4.5, None, 6.8],
        "strings": ["a", None, "c"],
        "datetimes": [
            datetime(2020, 1, 1),
            None,
            datetime(2020, 1, 3),
        ],
        "lists": [[1, 2], None, [3]],
    })


@pytest.mark.parametrize("name", NAMES)
def test_registers_each_recorder_under_its_dotted_name(name: str) -> None:
    """Each recorder is discoverable by its `polars.<format>` name."""
    assert name in recorders.RECORDER_REGISTRY


def test_registrations_keep_the_plugin_contract() -> None:
    """No contract problem involves a polars recorder."""
    affected = {n for p in recorders.RECORDER_REGISTRY.problems for n in p.names}

    assert affected.isdisjoint(NAMES)


@pytest.mark.parametrize("name", NAMES)
def test_derives_a_namespaced_mark_for_each_recorder(name: str) -> None:
    """`ditto.polars.<format>` is the mark for `record("polars.<format>")`."""
    fmt = name.removeprefix("polars.")

    actual = getattr(ditto.polars, fmt)

    expected = pytest.mark.record(name)
    assert actual == expected


@ditto.polars.parquet
def test_parquet_mark_selects_the_parquet_recorder(snapshot) -> None:
    """The parquet mark gives the snapshot fixture the parquet recorder, named
    `polars.parquet` in snapshot filenames."""
    actual = snapshot.recorder

    assert actual is recorders.get("polars.parquet")
    assert snapshot.recorder_name == "polars.parquet"


@pytest.mark.parametrize("name", NAMES)
def test_round_trips_a_dataframe(name: str) -> None:
    """Each recorder loads back exactly the DataFrame it saved."""
    df = _sample_dataframe()
    recorder = recorders.get(name)
    actual = recorder.loads(recorder.dumps(df))

    pl.testing.assert_frame_equal(actual, df)


@pytest.mark.parametrize("name", ["polars.parquet", "polars.ipc"])
def test_round_trips_nulls_datetimes_and_lists(name: str) -> None:
    """Parquet and IPC preserve nulls, datetimes, and list columns."""
    df = _rich_dataframe()
    recorder = recorders.get(name)
    actual = recorder.loads(recorder.dumps(df))

    pl.testing.assert_frame_equal(actual, df)


# ── Committed snapshots ───────────────────────────────────────────────────────

SNAPSHOTS = Path(__file__).parent / ".ditto"


def _recorder_name(path: Path) -> str:
    """The recorder name that ends a snapshot filename, e.g. `polars.csv`."""
    return path.name.rpartition("@")[2].partition(".")[2]


@pytest.mark.parametrize(
    "path",
    [
        p
        for p in sorted(SNAPSHOTS.iterdir())
        if _recorder_name(p) in {"polars.csv", "polars.ndjson"}
    ],
    ids=lambda p: p.name,
)
def test_rewriting_a_committed_text_snapshot_reproduces_its_bytes(path: Path) -> None:
    """Loading a committed snapshot and dumping it again gives the same bytes."""
    recorder = recorders.get(_recorder_name(path))
    raw = path.read_bytes()

    actual = recorder.dumps(recorder.loads(raw))

    assert actual == raw
