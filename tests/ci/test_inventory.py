from pathlib import Path

from ditto._inventory import (
    InventoryError,
    _find_lock,
    _lock_remote,
    _walk_local,
    build_inventory,
    lock_present,
)
from ditto._lockfile import (
    LOCKFILE_VERSION,
    LockEntry,
    LockFile,
    LockTarget,
    storage_key,
    write_lockfile,
)
from ditto.exceptions import DittoWarning

import pytest


def _write_snapshot(ditto_dir, name, data=b"xx"):
    ditto_dir.mkdir(parents=True, exist_ok=True)
    (ditto_dir / name).write_bytes(data)


def test_walk_local_reads_real_sizes_including_orphans(tmp_path):
    """Local walk reports on-disk files with real sizes, even ones not in a lock."""
    _write_snapshot(tmp_path / ".ditto", "mod.test_a@k.pkl", b"abcd")

    backends = _walk_local(tmp_path, lock=None, rootdir=None)

    entries = [e for b in backends for e in b.entries]
    assert len(entries) == 1
    assert entries[0].storage_key == "mod.test_a@k.pkl"
    assert entries[0].size_bytes == 4
    assert entries[0].modified is not None


def test_build_inventory_skips_snapshot_that_disappears_before_stat(
    tmp_path, monkeypatch
) -> None:
    """A concurrent snapshot deletion does not fail the remaining inventory."""
    snapshot = tmp_path / ".ditto" / "mod.test_a@k.pkl"
    _write_snapshot(snapshot.parent, snapshot.name)
    original_stat = Path.stat

    def stat_with_disappearing_snapshot(path, *args, **kwargs):
        if path == snapshot:
            raise FileNotFoundError(snapshot)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat_with_disappearing_snapshot)

    actual = build_inventory(tmp_path, live=False)

    assert actual == []


def test_build_inventory_fails_when_snapshot_metadata_is_unreadable(
    tmp_path, monkeypatch
) -> None:
    """A permission failure is reported instead of yielding a partial inventory."""
    snapshot = tmp_path / ".ditto" / "mod.test_a@k.pkl"
    _write_snapshot(snapshot.parent, snapshot.name)
    original_stat = Path.stat

    def stat_with_unreadable_snapshot(path, *args, **kwargs):
        if path == snapshot:
            raise PermissionError("permission denied")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat_with_unreadable_snapshot)

    with pytest.raises(InventoryError, match=str(snapshot)):
        build_inventory(tmp_path, live=False)


def test_build_inventory_reads_absolute_file_target_owned_by_scoped_test(
    tmp_path,
) -> None:
    """A scoped inventory includes an owning test's absolute external target."""
    project = tmp_path / "project"
    project.mkdir()
    target = tmp_path / "external-snapshots"
    entry = LockEntry(
        nodeid="test_external.py::test_external",
        key="value",
        recorder="pkl",
    )
    _write_snapshot(target, storage_key(entry, "file"), b"external")
    lock = LockFile(
        version=LOCKFILE_VERSION,
        targets={
            target.as_uri(): LockTarget(scheme="file", entries=(entry,)),
        },
    )
    write_lockfile(project / "ditto.lock", lock)

    manifest = build_inventory(project, live=False)

    assert [backend.location for backend in manifest] == [str(target)]
    assert [item.storage_key for backend in manifest for item in backend.entries] == [
        storage_key(entry, "file")
    ]


def test_build_inventory_reads_file_target_outside_requested_test_path(
    tmp_path,
) -> None:
    """A test-scoped inventory includes its project-level shared file target."""
    project = tmp_path / "project"
    test_path = project / "tests" / "unit"
    test_path.mkdir(parents=True)
    target = project / "snapshots"
    entry = LockEntry(
        nodeid="tests/unit/test_example.py::test_example",
        key="value",
        recorder="pkl",
    )
    _write_snapshot(target, storage_key(entry, "file"))
    lock = LockFile(
        version=LOCKFILE_VERSION,
        targets={
            "snapshots": LockTarget(scheme="file", entries=(entry,)),
        },
    )
    write_lockfile(project / "ditto.lock", lock)

    manifest = build_inventory(test_path, live=False)

    assert [backend.location for backend in manifest] == [str(target)]
    assert [item.storage_key for backend in manifest for item in backend.entries] == [
        storage_key(entry, "file")
    ]


def test_lock_remote_yields_unknown_size_entries(tmp_path):
    """Remote lock targets become entries with size/mtime None."""
    lock = LockFile(
        version=LOCKFILE_VERSION,
        targets={
            "redis://localhost:6379/0": LockTarget(
                scheme="redis",
                entries=(
                    LockEntry(nodeid="test_x.py::test_a", key="k", recorder="pkl"),
                ),
            )
        },
    )

    backends = _lock_remote(lock, tmp_path, rootdir=tmp_path)

    entries = [e for b in backends for e in b.entries]
    assert len(entries) == 1
    assert entries[0].size_bytes is None
    assert entries[0].modified is None


def test_lock_remote_scopes_entries_to_path(tmp_path):
    """Only lock entries whose test file is under PATH are inventoried."""
    lock = LockFile(
        version=LOCKFILE_VERSION,
        targets={
            "redis://h/0": LockTarget(
                scheme="redis",
                entries=(
                    LockEntry(nodeid="sub/test_in.py::test_a", key="k", recorder="pkl"),
                    LockEntry(
                        nodeid="other/test_out.py::test_b", key="k", recorder="pkl"
                    ),
                ),
            )
        },
    )

    backends = _lock_remote(lock, tmp_path / "sub", rootdir=tmp_path)

    keys = [e.storage_key for b in backends for e in b.entries]
    assert any("test_in" in k for k in keys)
    assert not any("test_out" in k for k in keys)


def test_find_lock_searches_ancestors(tmp_path):
    """_find_lock walks upward from PATH to locate ditto.lock."""
    (tmp_path / "ditto.lock").write_text("{}")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)

    assert _find_lock(nested) == tmp_path / "ditto.lock"
    assert _find_lock(tmp_path / "a") == tmp_path / "ditto.lock"


def test_find_lock_returns_none_when_absent(tmp_path):
    """_find_lock returns None when no ditto.lock governs PATH."""
    assert _find_lock(tmp_path) is None


def test_build_inventory_live_uses_introspect_only(tmp_path, monkeypatch):
    """live=True delegates to run_introspect and does not walk the disk."""
    sentinel = ["SENTINEL"]
    called = {}

    def fake_introspect(path):
        called["path"] = path
        return sentinel

    monkeypatch.setattr("ditto._inventory.run_introspect", fake_introspect)

    result = build_inventory(tmp_path, live=True)

    assert result is sentinel
    assert called["path"] == tmp_path


def test_build_inventory_default_never_introspects(tmp_path, monkeypatch):
    """Default (credential-free) build never spawns the pytest pass."""
    _write_snapshot(tmp_path / ".ditto", "mod.test_a@k.pkl")

    def boom(path):
        raise AssertionError("run_introspect must not be called by default")

    monkeypatch.setattr("ditto._inventory.run_introspect", boom)

    backends = build_inventory(tmp_path, live=False)

    keys = [e.storage_key for b in backends for e in b.entries]
    assert "mod.test_a@k.pkl" in keys


def test_build_inventory_degrades_on_corrupt_lock(tmp_path):
    """A corrupt ditto.lock warns and degrades to a local-only inventory."""
    _write_snapshot(tmp_path / ".ditto", "mod.test_a@k.pkl")
    (tmp_path / "ditto.lock").write_text("{ not json")

    with pytest.warns(DittoWarning):
        backends = build_inventory(tmp_path, live=False)

    keys = [e.storage_key for b in backends for e in b.entries]
    assert "mod.test_a@k.pkl" in keys


def test_lock_present_reflects_lockfile(tmp_path):
    """lock_present is True only when a ditto.lock governs PATH."""
    assert lock_present(tmp_path) is False
    (tmp_path / "ditto.lock").write_text("{}")
    assert lock_present(tmp_path) is True
