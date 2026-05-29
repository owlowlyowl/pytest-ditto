import pytest

from ditto._lockfile import LockEntry, LockTarget, LockFile, serialise, deserialise
from ditto._lockfile import read_lockfile, write_lockfile
from ditto.exceptions import DittoLockFileError, DittoLockFileVersionError


def _canonical_sample() -> LockFile:
    return LockFile(
        version=1,
        targets={
            "tests/api/.ditto": LockTarget(
                scheme="file",
                entries=(
                    LockEntry("tests/test_api.py::test_create", "headers", "json"),
                    LockEntry("tests/test_api.py::test_create", "payload", "json"),
                ),
            )
        },
    )


def test_round_trips_to_equal_lockfile():
    """Decoding an encoded lock file yields an equal value."""
    lock = _canonical_sample()

    actual = deserialise(serialise(lock))

    assert actual == lock


def test_emits_entries_in_sorted_order_regardless_of_input_order():
    """Entries are serialised sorted so diffs stay stable across runs."""
    unsorted = LockFile(
        version=1,
        targets={
            "tests/api/.ditto": LockTarget(
                scheme="file",
                entries=(
                    LockEntry("tests/test_api.py::test_create", "payload", "json"),
                    LockEntry("tests/test_api.py::test_create", "headers", "json"),
                ),
            )
        },
    )

    actual = deserialise(serialise(unsorted)).targets["tests/api/.ditto"].entries

    expected = (
        LockEntry("tests/test_api.py::test_create", "headers", "json"),
        LockEntry("tests/test_api.py::test_create", "payload", "json"),
    )
    assert actual == expected


def test_serialises_byte_stable_across_repeated_calls():
    """Serialising the same lock file twice produces identical bytes."""
    lock = _canonical_sample()

    assert serialise(lock) == serialise(lock)


def test_raises_when_version_is_unknown():
    """An unsupported lock-file version is rejected, not silently misparsed."""
    future = b'{"version": 999, "targets": {}}'

    with pytest.raises(DittoLockFileVersionError):
        deserialise(future)


def test_returns_none_when_lockfile_is_absent(tmp_path):
    """A missing lock file reads as None, not an error."""
    assert read_lockfile(tmp_path / "ditto.lock") is None


def test_round_trips_through_disk(tmp_path):
    """Writing then reading a lock file returns an equal value."""
    path = tmp_path / "ditto.lock"
    lock = _canonical_sample()

    write_lockfile(path, lock)
    actual = read_lockfile(path)

    assert actual == lock


def test_leaves_no_temp_file_after_write(tmp_path):
    """The atomic write cleans up its temporary file."""
    write_lockfile(tmp_path / "ditto.lock", _canonical_sample())

    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "ditto.lock"]
    assert leftovers == []


def test_raises_when_lockfile_is_corrupt(tmp_path):
    """A present but unparseable lock file fails loudly rather than reading empty."""
    path = tmp_path / "ditto.lock"
    path.write_bytes(b"{not json")

    with pytest.raises(DittoLockFileError):
        read_lockfile(path)
