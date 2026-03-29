import pytest

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
