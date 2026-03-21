import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from ditto import Snapshot
from ditto.recorders._json import json as json_recorder
from ditto.snapshot import load_snapshot, save_snapshot


# --- Snapshot dataclass ---


def test_filepath_combines_group_name_key_and_recorder_extension() -> None:
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


def test_save_snapshot_creates_file_on_disk(tmp_dir) -> None:
    """save_snapshot writes the snapshot file to the configured path."""
    key = "langford-skolem-pair"
    snapshot = Snapshot(path=tmp_dir, group_name="group")

    save_snapshot(snapshot, 41312432, key)

    assert snapshot.filepath(key).exists()


def test_save_snapshot_creates_output_directory_if_absent(tmp_dir) -> None:
    """save_snapshot creates the snapshot directory when it does not already exist."""
    path = tmp_dir / "nested" / "output"
    snapshot = Snapshot(path=path, group_name="group")

    save_snapshot(snapshot, 42, "key")

    assert path.exists()


# --- load_snapshot ---


def test_load_snapshot_returns_stored_value(tmp_dir) -> None:
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
    """Calling snapshot with an existing file returns the stored value, not the argument."""
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
