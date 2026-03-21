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
def test_recorder_saves_file_to_disk(tmp_dir, data, recorder: recorders.Recorder) -> None:
    """Each built-in recorder writes a file to the given path."""
    filepath = tmp_dir / f"tmp.{recorder.extension}"

    recorder.save(data, filepath)

    assert filepath.exists()
