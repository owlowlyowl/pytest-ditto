import pytest

ditto_pyarrow = pytest.importorskip("ditto_pyarrow")

import ditto  # noqa: E402
import pyarrow as pa  # noqa: E402

from ditto import recorders  # noqa: E402


def _make_table() -> pa.Table:
    return pa.table({
        "ints": [1, 2, 3],
        "floats": [4.5, 5.2, 6.8],
        "strings": ["a", "b", "c"],
    })


@pytest.mark.parametrize(
    "recorder_name", ["pyarrow_parquet", "pyarrow_feather", "pyarrow_csv"]
)
def test_pyarrow_recorder_is_registered(recorder_name: str) -> None:
    """Each pyarrow recorder is discoverable via the module-level registry."""
    assert recorder_name in recorders.RECORDER_REGISTRY


def test_pyarrow_marks_are_accessible() -> None:
    """ditto.pyarrow marks are accessible when the plugin is installed."""
    marks = ditto.pyarrow
    assert hasattr(marks, "parquet")
    assert hasattr(marks, "feather")
    assert hasattr(marks, "csv")


@ditto.pyarrow.parquet
def test_parquet_mark(snapshot) -> None:
    """The parquet mark selects the pyarrow_parquet recorder via the snapshot fixture."""
    table = _make_table()
    snapshot(table, key="parquet")
    assert snapshot.recorder.extension == "parquet"


@ditto.pyarrow.feather
def test_feather_mark(snapshot) -> None:
    """The feather mark selects the pyarrow_feather recorder via the snapshot fixture."""
    table = _make_table()
    snapshot(table, key="feather")
    assert snapshot.recorder.extension == "feather"


@ditto.pyarrow.csv
def test_csv_mark(snapshot) -> None:
    """The csv mark selects the pyarrow_csv recorder via the snapshot fixture."""
    table = _make_table()
    snapshot(table, key="csv")
    assert snapshot.recorder.extension == "csv"


@pytest.mark.parametrize(
    "recorder_name", ["pyarrow_parquet", "pyarrow_feather", "pyarrow_csv"]
)
def test_pyarrow_recorder_roundtrip_preserves_value(
    tmp_dir, recorder_name: str
) -> None:
    """Each pyarrow recorder round-trips a Table without loss."""
    table = _make_table()
    recorder = recorders.get(recorder_name)
    filepath = tmp_dir / f"tmp.{recorder.extension}"

    recorder.save(table, filepath)
    actual = recorder.load(filepath)

    assert actual.equals(table)
