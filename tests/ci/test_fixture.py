from pathlib import Path

import pytest

from ditto import Snapshot


TEST_DATA_DIR = Path(__file__).parent / ".ditto" 


def test_snapshot_fixture_exists(snapshot) -> None:
    assert True


def test_fixture_type(snapshot) -> None:
    assert isinstance(snapshot, Snapshot)


def test_exception_raised_when_no_key_specified(snapshot):
    with pytest.raises(TypeError) as excinfo:
        snapshot(1)
    assert excinfo.match(
        r"^Snapshot.__call__().*missing 1 required positional argument: 'key'"
    )


def test_snapshot_write(snapshot) -> None:
    key = "write"

    # Make sure the snapshot file does not exist before testing write.
    path_snapshot = TEST_DATA_DIR / f"test_snapshot_write@{key}.pkl"
    assert not path_snapshot.exists()

    try:
        value = "write-value"
        assert value == snapshot(value, key=key)

    finally:
        # remove the file for the next test run.
        path_snapshot.unlink()


def test_snapshot_read(snapshot) -> None:
    key = "read"

    # To test snapshot read; need to make sure file exists first.
    # path_snapshot = TEST_DATA_DIR / f"test_snapshot_read@{key}.pkl"
    # assert path_snapshot.exists()

    value = "read-value"
    assert value == snapshot(value, key=key)


def test_snapshot_used_twice_different_keys(snapshot) -> None:
    snapshot(77, key="a")
    snapshot("(>'.')>", key="b")


