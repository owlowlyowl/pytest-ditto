"""The pyarrow recorders, as registered through the 2.0 plugin contract."""

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
def test_persists_under_an_identifier_equal_to_its_name(name: str) -> None:
    """Snapshot files carry the recorder's name as their identifier."""
    actual = recorders.get(name).identifier

    expected = name
    assert actual == expected


@pytest.mark.parametrize("name", NAMES)
def test_derives_a_namespaced_mark_for_each_recorder(name: str) -> None:
    """`ditto.pyarrow.<format>` is the mark for `record("pyarrow.<format>")`."""
    fmt = name.removeprefix("pyarrow.")

    actual = getattr(ditto.pyarrow, fmt)

    expected = pytest.mark.record(name)
    assert actual == expected


@ditto.pyarrow.parquet
def test_parquet_mark_selects_the_parquet_recorder(snapshot) -> None:
    """The parquet mark gives the snapshot fixture the parquet recorder."""
    actual = snapshot.recorder

    assert actual is recorders.get("pyarrow.parquet")


@pytest.mark.parametrize("name", NAMES)
def test_round_trips_a_table(tmp_path, name: str) -> None:
    """Each recorder loads back exactly the table it saved."""
    table = _make_table()
    recorder = recorders.get(name)
    filepath = tmp_path / f"table.{recorder.identifier}"

    recorder.save(table, filepath)
    actual = recorder.load(filepath)

    assert actual.equals(table)
