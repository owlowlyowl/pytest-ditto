"""Credential-free CLI inventory: read snapshots from disk and the lock file.

The read-only inventory commands (`list`, `status`, `stats`, `lint`) assemble a
`Manifest` from the cheapest credential-free source per target:

- local `file` targets are read from the filesystem (real size and mtime,
  including orphans not in the lock);
- remote (non-`file`) targets are read from the committed `ditto.lock` (the
  declared set; size and mtime are unknown without a live backend connection).

`--live` selects the pytest introspection pass instead, for authoritative
physical state across every target.
"""

from __future__ import annotations

import warnings
from pathlib import Path

from ._cli_introspect import run_introspect
from ._lockfile import LOCKFILE_NAME, LockFile, read_lockfile, storage_key
from ._manifest import BackendManifest, Manifest, ManifestEntry
from .exceptions import DittoLockFileError, DittoWarning


__all__ = ("build_inventory", "lock_present")


def _find_lock(path: Path) -> Path | None:
    """Search `path` and its ancestors for `ditto.lock`; return it or `None`."""
    start = path.resolve()
    for directory in (start, *start.parents):
        candidate = directory / LOCKFILE_NAME
        if candidate.is_file():
            return candidate
    return None


def lock_present(path: Path) -> bool:
    """Return whether a `ditto.lock` governs `path` (for the no-lock hint)."""
    return _find_lock(path) is not None


def _is_within(resolved: Path, base: Path) -> bool:
    """Return whether `resolved` is `base` itself or nested under it."""
    return resolved == base or base in resolved.parents


def _nodeid_under(nodeid: str, rootdir: Path, base: Path) -> bool:
    """Return whether a lock entry's test file falls under `base` (the PATH)."""
    file_part = nodeid.split("::", 1)[0]
    resolved = (rootdir / file_part).resolve()
    return _is_within(resolved, base)


def _walk_local(path: Path, lock: LockFile | None, rootdir: Path | None) -> Manifest:
    """Inventory local `file` snapshots from disk under `path`.

    Walks every `.ditto/` directory under `path`, plus any `file`-scheme target
    directory recorded in `lock` that falls under `path` (deduplicated by
    resolved path). Each file is stat'd for real size and mtime, so on-disk
    orphans absent from the lock still appear.

    Parameters
    ----------
    path
        The directory to inventory.
    lock
        The parsed lock file, or `None` when absent or unreadable.
    rootdir
        The directory containing `ditto.lock`, used to resolve relative target
        ids, or `None` when there is no lock.

    Returns
    -------
    Manifest
        One `BackendManifest` per non-empty `.ditto/` directory.
    """
    base = path.resolve()
    dirs: dict[Path, None] = {}
    for ditto_dir in base.rglob(".ditto"):
        if ditto_dir.is_dir():
            dirs[ditto_dir.resolve()] = None
    if lock is not None and rootdir is not None:
        for target_id, target in lock.targets.items():
            if target.scheme != "file":
                continue
            resolved = (rootdir / target_id).resolve()
            if resolved.is_dir() and _is_within(resolved, base):
                dirs[resolved] = None

    backends: Manifest = []
    for directory in dirs:
        entries: list[ManifestEntry] = []
        for child in sorted(directory.iterdir()):
            if not child.is_file():
                continue
            try:
                stat = child.stat()
            except OSError:
                continue  # vanished between listing and stat (e.g. concurrent prune)
            entries.append(
                ManifestEntry(
                    storage_key=child.name,
                    size_bytes=stat.st_size,
                    modified=stat.st_mtime,
                )
            )
        if entries:
            backends.append(BackendManifest(location=str(directory), entries=entries))
    return backends


def _lock_remote(lock: LockFile | None, path: Path, rootdir: Path | None) -> Manifest:
    """Inventory remote (non-`file`) targets from the lock, scoped to `path`.

    Each entry whose test file falls under `path` becomes a `ManifestEntry` with
    `size_bytes=None` and `modified=None` (physical metadata is unknown without a
    live backend connection).

    Parameters
    ----------
    lock
        The parsed lock file, or `None` when absent or unreadable.
    path
        The directory the inventory is scoped to.
    rootdir
        The directory containing `ditto.lock`, used to resolve nodeids, or
        `None` when there is no lock.

    Returns
    -------
    Manifest
        One `BackendManifest` per remote target with in-scope entries.
    """
    if lock is None or rootdir is None:
        return []
    base = path.resolve()
    backends: Manifest = []
    for target_id, target in lock.targets.items():
        if target.scheme == "file":
            continue
        entries = [
            ManifestEntry(
                storage_key=storage_key(entry, target.scheme),
                size_bytes=None,
                modified=None,
            )
            for entry in target.entries
            if _nodeid_under(entry.nodeid, rootdir, base)
        ]
        if entries:
            backends.append(BackendManifest(location=target_id, entries=entries))
    return backends


def build_inventory(path: Path, *, live: bool) -> Manifest:
    """Assemble the snapshot inventory for `path`.

    By default reads credential-free from the filesystem (local) and `ditto.lock`
    (remote). With `live=True`, runs the pytest introspection pass for
    authoritative physical state across every target.

    Parameters
    ----------
    path
        The directory to inventory.
    live
        When `True`, delegate to the live introspection pass; otherwise build the
        credential-free inventory from disk and the lock file.

    Returns
    -------
    Manifest
        The assembled inventory.
    """
    if live:
        return run_introspect(path)
    lock_path = _find_lock(path)
    rootdir = lock_path.parent if lock_path is not None else None
    lock: LockFile | None = None
    if lock_path is not None:
        try:
            lock = read_lockfile(lock_path)
        except DittoLockFileError as exc:
            warnings.warn(
                f"{LOCKFILE_NAME} is unreadable ({exc}); showing local snapshots "
                "only — use --live for the full inventory.",
                category=DittoWarning,
                stacklevel=2,
            )
            lock = None
    return _walk_local(path, lock, rootdir) + _lock_remote(lock, path, rootdir)
