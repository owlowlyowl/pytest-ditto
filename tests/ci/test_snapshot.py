import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from ditto import Snapshot, recorders
from ditto.exceptions import DuplicateSnapshotKeyError
from ditto.snapshot import load_snapshot, save_snapshot

json_recorder = recorders.get("json")


# --- Snapshot dataclass ---


def test_filepath_encodes_group_name_key_and_extension() -> None:
    """The snapshot filepath encodes the group name, key, and recorder extension."""
    key = "yek"
    group_name = "puorg"
    snapshot = Snapshot(path=Path(__file__).parent, group_name=group_name)

    actual = snapshot.filepath(key)

    assert actual == Path(__file__).parent / f"{group_name}@{key}.pkl"


def test_filepath_reflects_recorder_extension() -> None:
    """Filepath extension matches the extension of the configured recorder."""
    snapshot = Snapshot(path=Path("/tests"), group_name="test", recorder=json_recorder)

    actual = snapshot.filepath("key")

    assert actual.suffix == ".json"


def test_snapshot_is_immutable() -> None:
    """Snapshot rejects attribute assignment — frozen dataclass contract."""
    snapshot = Snapshot(path=Path("/tests"), group_name="test")

    with pytest.raises(FrozenInstanceError):
        snapshot.group_name = "other"


# --- save_snapshot ---


def test_writes_snapshot_to_disk(tmp_dir) -> None:
    """save_snapshot writes the snapshot file to the configured path."""
    key = "langford-skolem-pair"
    snapshot = Snapshot(path=tmp_dir, group_name="group")

    save_snapshot(snapshot, 41312432, key)

    assert snapshot.filepath(key).exists()


def test_creates_output_directory_when_path_does_not_exist(tmp_dir) -> None:
    """save_snapshot creates the snapshot directory when it does not already exist."""
    path = tmp_dir / "nested" / "output"
    snapshot = Snapshot(path=path, group_name="group")

    save_snapshot(snapshot, 42, "key")

    assert path.exists()


# --- load_snapshot ---


def test_raises_when_snapshot_file_is_absent(tmp_dir) -> None:
    """load_snapshot raises FileNotFoundError when the snapshot file is absent."""
    snapshot = Snapshot(path=tmp_dir, group_name="group")

    with pytest.raises(FileNotFoundError):
        load_snapshot(snapshot, "missing-key")


def test_returns_deserialised_stored_value(tmp_dir) -> None:
    """load_snapshot deserialises and returns the value previously written to disk."""
    key = "A006877"
    group_name = "OEIS"
    value = [1, 2, 3, 6, 7, 9, 18, 25, 27, 54, 73, 97, 129, 171, 231, 313]

    with open(tmp_dir / f"{group_name}@{key}.json", "w") as f:
        json.dump(value, f)
    snapshot = Snapshot(path=tmp_dir, group_name=group_name, recorder=json_recorder)

    actual = load_snapshot(snapshot, key)

    assert actual == value


# --- resolve_snapshot (via __call__) ---


def test_saves_file_to_disk_on_first_call(tmp_dir) -> None:
    """Calling snapshot when no file exists writes the value to disk."""
    key = "A001844"
    snapshot = Snapshot(path=tmp_dir, group_name="OEIS")
    data = [1, 5, 13, 25, 41, 61, 85, 113, 145, 181, 221, 265, 313]

    snapshot(data, key)

    assert snapshot.filepath(key).exists()


def test_returns_data_on_first_call(tmp_dir) -> None:
    """Calling snapshot when no file exists returns the passed data."""
    key = "A001844"
    snapshot = Snapshot(path=tmp_dir, group_name="OEIS")
    data = [1, 5, 13, 25, 41, 61, 85, 113, 145, 181, 221, 265, 313]

    actual = snapshot(data, key)

    assert actual == data


def test_returns_stored_value_when_file_already_exists(tmp_dir) -> None:
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
    snapshot = Snapshot(path=tmp_dir, group_name=group_name, recorder=json_recorder)

    actual = snapshot(["something-different"], key)

    assert actual == stored


# --- update mode ---


def test_returns_new_value_when_update_is_true(tmp_dir) -> None:
    """When update=True, snapshot returns the new value rather than the stored one."""
    key = "result"
    snapshot = Snapshot(path=tmp_dir, group_name="group", update=True)
    save_snapshot(snapshot, "original", key)

    actual = snapshot("updated", key)

    assert actual == "updated"


def test_overwrites_stored_file_when_update_is_true(tmp_dir) -> None:
    """When update=True, snapshot replaces the value on disk."""
    key = "result"
    snapshot = Snapshot(path=tmp_dir, group_name="group", update=True)
    save_snapshot(snapshot, "original", key)

    snapshot("updated", key)

    assert load_snapshot(snapshot, key) == "updated"


# --- duplicate key detection ---


def test_raises_when_key_is_reused_within_same_snapshot(tmp_dir) -> None:
    """Calling snapshot twice with the same key raises DuplicateSnapshotKeyError."""
    snapshot = Snapshot(path=tmp_dir, group_name="group")
    snapshot(42, "result")

    with pytest.raises(DuplicateSnapshotKeyError):
        snapshot(99, "result")


def test_duplicate_key_error_names_the_offending_key(tmp_dir) -> None:
    """DuplicateSnapshotKeyError message identifies which key was reused."""
    snapshot = Snapshot(path=tmp_dir, group_name="group")
    snapshot(42, "result")

    with pytest.raises(DuplicateSnapshotKeyError, match="'result'"):
        snapshot(99, "result")


def test_does_not_raise_when_different_keys_are_used(tmp_dir) -> None:
    """snapshot accepts multiple calls within a test as long as each key is unique."""
    snapshot = Snapshot(path=tmp_dir, group_name="group")

    first = snapshot(1, "first")
    second = snapshot(2, "second")

    assert first == 1
    assert second == 2


def test_filepath_raises_type_error_for_backend_constructed_snapshot() -> None:
    """filepath() raises TypeError when the snapshot was built with backend=, not path=."""
    backend: dict[str, bytes] = {}
    snapshot = Snapshot(group_name="test", module="mod", backend=backend)

    with pytest.raises(TypeError, match="path-based"):
        snapshot.filepath("key")


def test_raises_at_construction_when_no_storage_target_is_given() -> None:
    """Snapshot raises TypeError immediately when neither path= nor backend= is provided."""
    with pytest.raises(TypeError, match="Snapshot requires a storage target"):
        Snapshot(group_name="test")
