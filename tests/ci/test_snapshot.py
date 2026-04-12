import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import fsspec
import pytest

from ditto import Snapshot, recorders
from ditto.backends import FsspecMapping
from ditto.exceptions import DuplicateSnapshotKeyError
from ditto.snapshot import load_snapshot, save_snapshot

json_recorder = recorders.get("json")
qualified_json_recorder = recorders.Recorder(
    extension="plugin.json",
    save=json_recorder.save,
    load=json_recorder.load,
)


def _file_snapshot(path: Path, **kwargs) -> Snapshot:
    """Create a file:// Snapshot backed by the given path."""
    resolved = path.resolve()
    return Snapshot(
        target=f"file://{resolved.as_posix()}",
        _backend=FsspecMapping(fsspec.filesystem("file"), resolved.as_posix()),
        group_name=kwargs.pop("group_name", "group"),
        module=kwargs.pop("module", ""),
        **kwargs,
    )


# --- Snapshot dataclass ---


def test_snapshot_is_immutable() -> None:
    """Snapshot rejects attribute assignment — frozen dataclass contract."""
    snapshot = _file_snapshot(Path("/tests"), group_name="test")

    with pytest.raises(FrozenInstanceError):
        snapshot.group_name = "other"


# --- save_snapshot ---


def test_writes_value_to_backend_on_save(tmp_dir) -> None:
    """save_snapshot persists the value so it can be loaded back."""
    key = "langford-skolem-pair"
    snapshot = _file_snapshot(tmp_dir, group_name="group")

    save_snapshot(snapshot, 41312432, key)

    assert load_snapshot(snapshot, key) == 41312432


def test_creates_output_directory_when_path_does_not_exist(tmp_dir) -> None:
    """save_snapshot creates the snapshot directory when it does not already exist."""
    path = tmp_dir / "nested" / "output"
    snapshot = _file_snapshot(path, group_name="group")

    save_snapshot(snapshot, 42, "key")

    assert path.exists()


# --- load_snapshot ---


def test_raises_when_snapshot_file_is_absent(tmp_dir) -> None:
    """load_snapshot raises FileNotFoundError when the snapshot file is absent."""
    snapshot = _file_snapshot(tmp_dir, group_name="group")

    with pytest.raises(FileNotFoundError):
        load_snapshot(snapshot, "missing-key")


def test_returns_deserialised_stored_value(tmp_dir) -> None:
    """load_snapshot deserialises and returns the value previously written to disk."""
    key = "A006877"
    group_name = "OEIS"
    value = [1, 2, 3, 6, 7, 9, 18, 25, 27, 54, 73, 97, 129, 171, 231, 313]

    with open(tmp_dir / f"{group_name}@{key}.json", "w") as f:
        json.dump(value, f)
    snapshot = _file_snapshot(tmp_dir, group_name=group_name, recorder=json_recorder)

    actual = load_snapshot(snapshot, key)

    assert actual == value


# --- resolve_snapshot (via __call__) ---


def test_saves_value_to_backend_on_first_call(tmp_dir) -> None:
    """Calling snapshot when no file exists writes the value and returns it."""
    key = "A001844"
    snapshot = _file_snapshot(tmp_dir, group_name="OEIS")
    data = [1, 5, 13, 25, 41, 61, 85, 113, 145, 181, 221, 265, 313]

    result = snapshot(data, key)

    assert load_snapshot(snapshot, key) == data
    assert result == data


def test_returns_stored_value_when_snapshot_already_exists(tmp_dir) -> None:
    """snapshot returns the stored value, not the argument, when the file exists."""
    key = "rainbow"
    group_name = "colours"
    stored = [
        "#ff0000",
        "#ffa500",
        "#ffff00",
        "#008000",
        "#0000ff",
        "#4b0082",
    ]

    with open(tmp_dir / f"{group_name}@{key}.json", "w") as f:
        json.dump(stored, f)
    snapshot = _file_snapshot(tmp_dir, group_name=group_name, recorder=json_recorder)

    actual = snapshot(["something-different"], key)

    assert actual == stored


def test_file_backed_snapshot_preserves_dotted_recorder_identifier(tmp_dir) -> None:
    """A dotted recorder identifier is preserved in the persisted snapshot name."""
    snapshot = _file_snapshot(
        tmp_dir,
        group_name="group",
        recorder=qualified_json_recorder,
    )

    actual = snapshot({"answer": 42}, "result")

    assert actual == {"answer": 42}
    assert (tmp_dir / "group@result.plugin.json").exists()
    assert load_snapshot(snapshot, "result") == {"answer": 42}


# --- update mode ---


def test_returns_new_value_when_update_is_true(tmp_dir) -> None:
    """When update=True, snapshot returns the new value rather than the stored one."""
    key = "result"
    snapshot = _file_snapshot(tmp_dir, group_name="group", update=True)
    save_snapshot(snapshot, "original", key)

    actual = snapshot("updated", key)

    assert actual == "updated"


def test_overwrites_stored_value_when_update_is_true(tmp_dir) -> None:
    """When update=True, snapshot replaces the value on disk."""
    key = "result"
    snapshot = _file_snapshot(tmp_dir, group_name="group", update=True)
    save_snapshot(snapshot, "original", key)

    snapshot("updated", key)

    assert load_snapshot(snapshot, key) == "updated"


# --- duplicate key detection ---


def test_raises_when_key_is_reused_within_same_snapshot(tmp_dir) -> None:
    """Calling snapshot twice with the same key raises DuplicateSnapshotKeyError."""
    snapshot = _file_snapshot(tmp_dir, group_name="group")
    snapshot(42, "result")

    with pytest.raises(DuplicateSnapshotKeyError):
        snapshot(99, "result")


def test_duplicate_key_error_names_the_offending_key(tmp_dir) -> None:
    """DuplicateSnapshotKeyError message identifies which key was reused."""
    snapshot = _file_snapshot(tmp_dir, group_name="group")
    snapshot(42, "result")

    with pytest.raises(DuplicateSnapshotKeyError, match="'result'"):
        snapshot(99, "result")


def test_does_not_raise_when_different_keys_are_used(tmp_dir) -> None:
    """snapshot accepts multiple calls within a test as long as each key is unique."""
    snapshot = _file_snapshot(tmp_dir, group_name="group")

    first = snapshot(1, "first")
    second = snapshot(2, "second")

    assert first == 1
    assert second == 2


# --- construction validation ---


def test_raises_at_construction_when_module_is_empty_for_non_file_scheme() -> None:
    """Snapshot raises TypeError when a non-file:// target is given without module=."""
    with pytest.raises(TypeError, match="module="):
        Snapshot(
            group_name="test",
            module="",
            target="memory://",
            _backend={},
        )


def test_accepts_empty_module_for_file_scheme(tmp_dir) -> None:
    """Snapshot allows module='' for file:// targets — module is implicit in path."""
    snapshot = _file_snapshot(tmp_dir, group_name="test", module="")

    assert snapshot.module == ""
