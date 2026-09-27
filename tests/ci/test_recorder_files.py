"""`recorder_from_files`: adapting file-based libraries to the byte interface."""

import json
from pathlib import Path
from typing import Any

import pytest

from ditto.recorders import Recorder, recorder_from_files


def _save(value: Any, path: Path) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_round_trips_through_the_files_library() -> None:
    recorder = recorder_from_files(save=_save, load=_load, suffix=".json")

    actual = recorder.loads(recorder.dumps({"a": [1, 2]}))

    assert isinstance(recorder, Recorder)
    assert actual == {"a": [1, 2]}


def test_dumps_returns_the_file_the_library_wrote() -> None:
    recorder = recorder_from_files(save=_save, load=_load, suffix=".json")

    actual = recorder.dumps({"a": 1})

    assert actual == b'{"a": 1}'


def test_gives_the_library_a_path_with_the_suffix() -> None:
    seen: list[Path] = []

    def save(value: Any, path: Path) -> None:
        seen.append(path)
        _save(value, path)

    recorder_from_files(save=save, load=_load, suffix=".parquet").dumps(1)

    (path,) = seen
    assert path.name == "snapshot.parquet"


def test_removes_the_temporary_directory_after_each_call() -> None:
    seen: list[Path] = []

    def save(value: Any, path: Path) -> None:
        seen.append(path)
        _save(value, path)

    def load(path: Path) -> Any:
        seen.append(path)
        return _load(path)

    recorder = recorder_from_files(save=save, load=load, suffix=".json")
    recorder.loads(recorder.dumps(1))

    assert len(seen) == 2
    assert not any(path.parent.exists() for path in seen)


@pytest.mark.parametrize("failing", ["save", "load"])
def test_removes_the_temporary_directory_when_the_library_fails(failing: str) -> None:
    seen: list[Path] = []

    def fail(*args: Any) -> Any:
        seen.append(args[-1])
        raise RuntimeError("library failed")

    functions = {"save": _save, "load": _load, failing: fail}
    recorder = recorder_from_files(**functions, suffix=".json")

    with pytest.raises(RuntimeError, match="library failed"):
        if failing == "save":
            recorder.dumps(1)
        else:
            recorder.loads(b"1")

    (path,) = seen
    assert not path.parent.exists()


@pytest.mark.parametrize("suffix", ["", "json", ".", "./x", ".a/b", ".a\\b"])
def test_rejects_a_suffix_that_is_not_a_filename_suffix(suffix: str) -> None:
    with pytest.raises(ValueError, match="filename suffix"):
        recorder_from_files(save=_save, load=_load, suffix=suffix)
