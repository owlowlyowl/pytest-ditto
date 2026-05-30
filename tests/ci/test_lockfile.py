from pathlib import Path

import fsspec
import pytest

from ditto._lockfile import LockEntry, LockTarget, LockFile, serialise, deserialise
from ditto._lockfile import read_lockfile, write_lockfile
from ditto._lockfile import portable_target_id, storage_key
from ditto._lockfile import merge_append
from ditto.exceptions import DittoLockFileError, DittoLockFileVersionError
from ditto.snapshot import _SessionTracker, LockSeen, Snapshot, resolve_snapshot, session_tracker
from ditto.backends import FsspecMapping
from ditto.recorders import default as _default_recorder


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


def test_relativises_file_uri_to_rootdir():
    """A file:// target becomes a rootdir-relative, machine-independent id."""
    actual = portable_target_id("file:///home/u/proj/tests/api/.ditto", Path("/home/u/proj"))

    expected = "tests/api/.ditto"
    assert actual == expected


def test_passes_remote_uri_through_unchanged():
    """A remote target id is the URI verbatim."""
    actual = portable_target_id("s3://bucket/snaps", Path("/home/u/proj"))

    expected = "s3://bucket/snaps"
    assert actual == expected


def test_derives_flat_dotted_key_for_file_scheme():
    """File backends use a flat dotted storage key."""
    entry = LockEntry("tests/test_api.py::TestX::test_foo", "result", "pkl")

    actual = storage_key(entry, "file")

    expected = "tests.test_api.TestX.test_foo@result.pkl"
    assert actual == expected


def test_derives_slash_namespaced_key_for_remote_scheme():
    """Remote backends use a slash-namespaced storage key."""
    entry = LockEntry("tests/test_api.py::TestX::test_foo", "result", "pkl")

    actual = storage_key(entry, "s3")

    expected = "tests/test_api/TestX.test_foo@result.pkl"
    assert actual == expected


def test_preserves_dotted_recorder_extension_in_key():
    """A dotted recorder ext (e.g. pandas.parquet) survives key derivation."""
    entry = LockEntry("tests/test_etl.py::test_pipe", "frame", "pandas.parquet")

    actual = storage_key(entry, "file")

    expected = "tests.test_etl.test_pipe@frame.pandas.parquet"
    assert actual == expected


def test_returns_file_uri_verbatim_when_outside_rootdir():
    """A file:// target outside the rootdir is returned unchanged (not portable)."""
    actual = portable_target_id("file:///elsewhere/.ditto", Path("/home/u/proj"))

    expected = "file:///elsewhere/.ditto"
    assert actual == expected


def test_unions_new_entry_without_dropping_existing():
    """Appending adds the new entry and keeps the existing ones."""
    new = LockEntry("tests/test_api.py::test_update", "body", "json")

    result = merge_append(_canonical_sample(), "tests/api/.ditto", "file", [new])

    entries = result.targets["tests/api/.ditto"].entries
    assert new in entries
    assert len(entries) == 3


def test_is_idempotent_for_a_duplicate_entry():
    """Appending an entry that already exists changes nothing."""
    existing = _canonical_sample()
    dup = existing.targets["tests/api/.ditto"].entries[0]

    result = merge_append(existing, "tests/api/.ditto", "file", [dup])

    assert len(result.targets["tests/api/.ditto"].entries) == 2


def test_creates_target_when_absent():
    """Appending to an unknown target creates it from scratch."""
    new = LockEntry("tests/test_x.py::test_y", "k", "pkl")

    result = merge_append(None, "tests/x/.ditto", "file", [new])

    assert result.version == 1
    assert result.targets["tests/x/.ditto"].entries == (new,)


def test_leaves_other_targets_untouched():
    """Appending to one target does not disturb the others."""
    new = LockEntry("tests/test_x.py::test_y", "k", "pkl")

    result = merge_append(_canonical_sample(), "s3://b/snaps", "s3", [new])

    assert "tests/api/.ditto" in result.targets
    assert "s3://b/snaps" in result.targets


def test_does_not_mutate_existing_lockfile():
    """merge_append returns a new value and leaves the input lock file unchanged."""
    original = _canonical_sample()
    before = dict(original.targets)

    merge_append(original, "tests/api/.ditto", "file", [LockEntry("a::b", "k", "pkl")])

    assert original.targets == before


def test_records_created_lock_entry_when_snapshot_is_new(tmp_path):
    """Creating a snapshot records a created lock entry for its target."""
    session_tracker.reset()
    backend = FsspecMapping(fsspec.filesystem("file"), (tmp_path / ".ditto").as_posix())
    snap = Snapshot(
        group_name="test_foo",
        module="tests/test_foo",
        target=f"file://{tmp_path}/.ditto",
        _backend=backend,
        recorder=_default_recorder(),
        nodeid="tests/test_foo.py::test_foo",
        target_id="tests/.ditto",
    )

    resolve_snapshot(snap, 123, "k")

    expected = LockSeen(
        target_id="tests/.ditto",
        scheme="file",
        nodeid="tests/test_foo.py::test_foo",
        key="k",
        recorder="pkl",
    )
    assert expected in session_tracker.lock_created
    session_tracker.reset()


def test_records_accessed_only_when_snapshot_already_exists(tmp_path):
    """Resolving an already-stored snapshot records access but not creation."""
    session_tracker.reset()
    backend = FsspecMapping(fsspec.filesystem("file"), (tmp_path / ".ditto").as_posix())
    snap = Snapshot(
        group_name="test_foo",
        module="tests/test_foo",
        target=f"file://{tmp_path}/.ditto",
        _backend=backend,
        recorder=_default_recorder(),
        nodeid="tests/test_foo.py::test_foo",
        target_id="tests/.ditto",
    )
    resolve_snapshot(snap, 123, "k")  # first call creates and records it
    session_tracker.reset()  # clear observations; the stored snapshot remains on disk

    resolve_snapshot(snap, 123, "k")

    seen = LockSeen(
        target_id="tests/.ditto",
        scheme="file",
        nodeid="tests/test_foo.py::test_foo",
        key="k",
        recorder="pkl",
    )
    assert seen in session_tracker.lock_accessed
    assert seen not in session_tracker.lock_created
    session_tracker.reset()


def test_records_entry_as_created_and_accessed_when_created():
    """A first-write observation is recorded as both created and accessed."""
    tracker = _SessionTracker()
    seen = LockSeen("tests/.ditto", "file", "tests/test_a.py::test_a", "k", "pkl")

    tracker.record_lock_seen(seen, created=True)

    assert seen in tracker.lock_created
    assert seen in tracker.lock_accessed


def test_records_entry_as_accessed_only_when_not_created():
    """Loading an existing snapshot records access but not creation."""
    tracker = _SessionTracker()
    seen = LockSeen("tests/.ditto", "file", "tests/test_a.py::test_a", "k", "pkl")

    tracker.record_lock_seen(seen, created=False)

    assert seen not in tracker.lock_created
    assert seen in tracker.lock_accessed


def test_clears_lock_sets_on_reset():
    """Resetting the tracker drops all recorded lock observations."""
    tracker = _SessionTracker()
    tracker.record_lock_seen(
        LockSeen("tests/.ditto", "file", "tests/test_a.py::test_a", "k", "pkl"),
        created=True,
    )

    tracker.reset()

    assert not tracker.lock_created
    assert not tracker.lock_accessed
