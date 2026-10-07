"""The pyarrow recorders, as registered through the 2.0 plugin contract."""

from pathlib import Path

import pyarrow as pa
import pytest

import ditto
from ditto import recorders

NAMES = ["pyarrow.parquet", "pyarrow.feather", "pyarrow.csv"]


def _make_table() -> pa.Table:
    return pa.table({
        "ints": [1, 2, 3],
        "floats": [4.5, 5.2, 6.8],
        "strings": ["a", "b", "c"],
    })


@pytest.mark.parametrize("name", NAMES)
def test_registers_each_recorder_under_its_dotted_name(name: str) -> None:
    """Each recorder is discoverable by its `pyarrow.<format>` name."""
    assert name in recorders.RECORDER_REGISTRY


def test_registrations_keep_the_plugin_contract() -> None:
    """No contract problem involves a pyarrow recorder."""
    affected = {n for p in recorders.RECORDER_REGISTRY.problems for n in p.names}

    assert affected.isdisjoint(NAMES)


@pytest.mark.parametrize("name", NAMES)
def test_derives_a_namespaced_mark_for_each_recorder(name: str) -> None:
    """`ditto.pyarrow.<format>` is the mark for `record("pyarrow.<format>")`."""
    fmt = name.removeprefix("pyarrow.")

    actual = getattr(ditto.pyarrow, fmt)

    expected = pytest.mark.record(name)
    assert actual == expected


@ditto.pyarrow.parquet
def test_parquet_mark_selects_the_parquet_recorder(snapshot) -> None:
    """The parquet mark gives the snapshot fixture the parquet recorder, named
    `pyarrow.parquet` in snapshot filenames."""
    actual = snapshot.recorder

    assert actual is recorders.get("pyarrow.parquet")
    assert snapshot.recorder_name == "pyarrow.parquet"


@pytest.mark.parametrize("name", NAMES)
def test_round_trips_a_table(name: str) -> None:
    """Each recorder loads back exactly the table it saved."""
    table = _make_table()
    recorder = recorders.get(name)
    actual = recorder.loads(recorder.dumps(table))

    assert actual.equals(table)


# ── Committed snapshots ───────────────────────────────────────────────────────

SNAPSHOTS = Path(__file__).parent / ".ditto"


def _recorder_name(path: Path) -> str:
    """The recorder name that ends a snapshot filename, e.g. `pyarrow.csv`."""
    return path.name.rpartition("@")[2].partition(".")[2]


@pytest.mark.parametrize(
    "path",
    [p for p in sorted(SNAPSHOTS.iterdir()) if _recorder_name(p) in {"pyarrow.csv"}],
    ids=lambda p: p.name,
)
def test_rewriting_a_committed_text_snapshot_reproduces_its_bytes(path: Path) -> None:
    """Loading a committed snapshot and dumping it again gives the same bytes."""
    recorder = recorders.get(_recorder_name(path))
    raw = path.read_bytes()

    actual = recorder.dumps(recorder.loads(raw))

    assert actual == raw
