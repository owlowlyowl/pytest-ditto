import pytest

ditto_pandas = pytest.importorskip("ditto_pandas")

import ditto  # noqa: E402
import pandas as pd  # noqa: E402

from ditto import recorders  # noqa: E402


@pytest.mark.parametrize(
    "recorder_name", ["pandas_parquet", "pandas_json", "pandas_csv"]
)
def test_pandas_recorder_is_registered(recorder_name: str) -> None:
    """Each pandas recorder is discoverable via the module-level registry."""
    assert recorder_name in recorders.RECORDER_REGISTRY


def test_pandas_marks_are_accessible() -> None:
    """ditto.pandas marks are accessible when the plugin is installed."""
    marks = ditto.pandas
    assert hasattr(marks, "parquet")
    assert hasattr(marks, "json")
    assert hasattr(marks, "csv")


@ditto.pandas.parquet
def test_parquet_mark(snapshot) -> None:
    """The parquet mark selects the pandas_parquet recorder via the snapshot fixture."""
    data = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    snapshot(data, key="parquet")
    assert snapshot.filepath("parquet").exists()
    assert snapshot.filepath("parquet").suffix == ".parquet"


@ditto.pandas.json
def test_json_mark(snapshot) -> None:
    """The json mark selects the pandas_json recorder via the snapshot fixture."""
    data = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    snapshot(data, key="json")
    assert snapshot.filepath("json").exists()
    assert snapshot.filepath("json").suffix == ".json"


@ditto.pandas.csv
def test_csv_mark(snapshot) -> None:
    """The csv mark selects the pandas_csv recorder via the snapshot fixture."""
    data = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    snapshot(data, key="csv")
    assert snapshot.filepath("csv").exists()
    assert snapshot.filepath("csv").suffix == ".csv"


@pytest.mark.parametrize(
    ("data", "recorder_name"),
    [
        pytest.param(
            pd.DataFrame({"a": [1, 2], "b": [3, 4]}), "pandas_parquet", id="parquet"
        ),
        pytest.param(
            pd.DataFrame({"a": [1, 2], "b": [3, 4]}), "pandas_json", id="json"
        ),
    ],
)
def test_pandas_recorder_roundtrip_preserves_value(
    tmp_dir, data: pd.DataFrame, recorder_name: str
) -> None:
    """Pandas parquet and json recorders round-trip a DataFrame without loss."""
    recorder = recorders.get(recorder_name)
    filepath = tmp_dir / f"tmp.{recorder.extension}"

    recorder.save(data, filepath)
    actual = recorder.load(filepath)

    pd.testing.assert_frame_equal(actual, data)


def test_pandas_csv_recorder_saves_file(tmp_dir) -> None:
    """Pandas CSV recorder writes a file to disk."""
    recorder = recorders.get("pandas_csv")
    data = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    filepath = tmp_dir / f"tmp.{recorder.extension}"

    recorder.save(data, filepath)

    assert filepath.exists()
