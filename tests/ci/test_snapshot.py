import shutil
import json
from pathlib import Path

import pytest

from ditto import Snapshot, io
from ditto.io._json import Json


TEST_DIR = Path(__file__).parent / "tmp-test_snapshot"


def test_snapshot_filepath() -> None:
    key = "yek"
    group_name = "pruop"
    path = Path(__file__).parent

    snapshot = Snapshot(path=path, group_name=group_name)

    # default filetype is pickle; hence, ".pkl" extension.
    assert snapshot.filepath(key) == path / f"{group_name}@{key}.pkl"


def test_snapshot_save(tmp_dir) -> None:
    key = "langford-skolem-pair"
    group_name = "group"

    snapshot = Snapshot(path=tmp_dir, group_name=group_name)

    assert not snapshot.filepath(
        key
    ).exists(), "No snapshot path should exist prior to calling save."
    snapshot.save(41312432, key)
    assert snapshot.filepath(key).exists(), "The snapshot should now exist."


def test_snapshot_load(tmp_dir) -> None:

    key = "A006877"
    group_name = "OEIS"

    # Create snapshot superficially before calling snapshot.load
    value = [1, 2, 3, 6, 7, 9, 18, 25, 27, 54, 73, 97, 129, 171, 231, 313]
    with open(tmp_dir / f"{group_name}@{key}.json", "w") as f:
        json.dump(value, f)

    snapshot = Snapshot(path=tmp_dir, group_name=group_name, io=Json)
    assert snapshot.filepath(
        key
    ).exists(), "Artificial snapshot should exist as part of test setup."

    result = snapshot.load(key)
    assert result == value


def test_snapshot_call_save(tmp_dir) -> None:
    key = "A001844"
    group_name = "OEIS"
    data = [1, 5, 13, 25, 41, 61, 85, 113, 145, 181, 221, 265, 313]

    snapshot = Snapshot(path=tmp_dir, group_name=group_name)

    assert not snapshot.filepath(
        key
    ).exists(), "No snapshot path should exist prior to calling save."
    snapshot(data, key)
    assert snapshot.filepath(key).exists(), "The snapshot should now exist."


def test_snapshot_call_load(monkeypatch, tmp_dir) -> None:
    # make sure nothing is happening with the save method
    monkeypatch.setattr("ditto.snapshot.Snapshot.save", lambda *args, **kwargs: None)

    key = "rainbow"
    group_name = "colours"

    # Create snapshot superficially before calling snapshot.load
    value = [
        "#ff0000",
        "#ffa500",
        "#ffff00",
        "#008000",
        "#0000ff",
        "#4b0082",
        "#ee82ee1",
    ]
    with open(tmp_dir / f"{group_name}@{key}.json", "w") as f:
        json.dump(value, f)

    snapshot = Snapshot(path=tmp_dir, group_name=group_name, io=Json)
    assert snapshot.filepath(
        key
    ).exists(), "Artificial snapshot should exist as part of test setup."

    result = snapshot(value, key)
    assert result == value
