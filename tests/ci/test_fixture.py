from pathlib import Path

import pytest

from ditto import Snapshot


TEST_DATA_DIR = Path(__file__).parent / ".ditto"


def test_fixture_returns_snapshot_instance(snapshot) -> None:
    """The snapshot fixture injects a Snapshot instance into the test."""
    assert isinstance(snapshot, Snapshot)


def test_raises_when_key_is_not_provided(snapshot) -> None:
    """snapshot raises TypeError when called without the required key argument."""
    with pytest.raises(TypeError) as excinfo:
        snapshot(1)
    assert excinfo.match(
        r"^Snapshot.__call__().*missing 1 required positional argument: 'key'"
    )


def test_returns_value_on_first_call(snapshot) -> None:
    """snapshot returns the value passed to it when no snapshot file exists yet."""
    key = "write"
    path_snapshot = TEST_DATA_DIR / f"test_returns_value_on_first_call@{key}.pkl"
    assert not path_snapshot.exists()

    try:
        actual = snapshot("write-value", key=key)
        assert actual == "write-value"
    finally:
        path_snapshot.unlink()


def test_returns_stored_value_on_subsequent_calls(snapshot) -> None:
    """snapshot returns the stored value, not the argument, when the file exists."""
    key = "read"

    # tests/ci/.ditto/test_returns_stored_value_on_subsequent_calls@read.pkl is
    # committed and contains "read-value". Passing a different argument proves the
    # stored value is returned rather than the argument.
    actual = snapshot("different-value", key=key)

    assert actual == "read-value"


def test_snapshot_used_twice_different_keys(snapshot) -> None:
    """snapshot can be called multiple times within a test using different keys."""
    snapshot(77, key="a")
    snapshot("(>'.')>", key="b")


def test_returns_value_when_key_is_an_integer(snapshot) -> None:
    """snapshot accepts an integer key and stores and returns the value correctly."""
    actual = snapshot(77, key=1029384756)

    assert actual == 77
