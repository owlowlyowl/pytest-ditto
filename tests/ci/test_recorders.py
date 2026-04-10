import json as _json
import pickle as _pickle

import pytest
import yaml as _yaml

from ditto import recorders


@pytest.mark.parametrize(
    ("data", "recorder"),
    [
        pytest.param(data, recorders.get(recorder_name), id=recorder_name)
        for data, recorder_name in [
            (1, "pickle"),
            (2, "json"),
            (3, "yaml"),
        ]
    ],
)
def test_recorder_saves_file_to_disk(
    tmp_dir, data, recorder: recorders.Recorder
) -> None:
    """Each built-in recorder writes a file to the given path."""
    filepath = tmp_dir / f"tmp.{recorder.extension}"

    recorder.save(data, filepath)

    assert filepath.exists()


@pytest.mark.parametrize(
    ("data", "recorder"),
    [
        pytest.param(data, recorders.get(recorder_name), id=f"{recorder_name}-{label}")
        for label, data in [
            ("dict", {"key": "value", "num": 42}),
            ("list", [1, "two", 3.0]),
            ("none", None),
        ]
        for recorder_name in ("pickle", "json", "yaml")
    ],
)
def test_recorder_roundtrip_preserves_value(
    tmp_dir, data, recorder: recorders.Recorder
) -> None:
    """Each built-in recorder round-trips data through save and load without loss."""
    filepath = tmp_dir / f"tmp.{recorder.extension}"

    recorder.save(data, filepath)
    actual = recorder.load(filepath)

    assert actual == data


# --- corrupt file handling ---


@pytest.mark.parametrize(
    ("content", "recorder", "exc"),
    [
        pytest.param(
            b"\x00", recorders.get("pickle"), _pickle.UnpicklingError, id="pickle"
        ),
        pytest.param(b"{", recorders.get("json"), _json.JSONDecodeError, id="json"),
        pytest.param(
            b"key: {unclosed", recorders.get("yaml"), _yaml.YAMLError, id="yaml"
        ),
    ],
)
def test_raises_when_file_is_corrupt(
    tmp_dir, content, recorder: recorders.Recorder, exc: type[Exception]
) -> None:
    """load raises a format-specific error rather than silently returning garbage."""
    filepath = tmp_dir / f"corrupt.{recorder.extension}"
    filepath.write_bytes(content)

    with pytest.raises(exc):
        recorder.load(filepath)


# --- known type limitations ---


@pytest.mark.parametrize(
    ("recorder_name",),
    [pytest.param("json", id="json"), pytest.param("yaml", id="yaml")],
)
def test_tuple_is_loaded_as_list(tmp_dir, recorder_name: str) -> None:
    """JSON and YAML have no tuple type; tuples saved by these recorders are loaded
    back as lists."""
    recorder = recorders.get(recorder_name)
    filepath = tmp_dir / f"tmp.{recorder.extension}"

    recorder.save((1, 2, 3), filepath)
    actual = recorder.load(filepath)

    assert actual == [1, 2, 3]
    assert type(actual) is list
