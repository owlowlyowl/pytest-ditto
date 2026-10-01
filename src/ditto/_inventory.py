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

import stat
import warnings
from pathlib import Path
from urllib.parse import urlparse

from ._cli_introspect import run_introspect
from ._lockfile import LOCKFILE_NAME, LockEntry, LockFile, read_lockfile, storage_key
from ._manifest import BackendManifest, Manifest, ManifestEntry
from .exceptions import DittoLockFileError, DittoWarning


__all__ = (
    "InventoryError",
    "build_inventory",
    "location_key",
    "lock_identities",
    "lock_present",
)


class InventoryError(RuntimeError):
    """Raised when a credential-free inventory cannot be read completely."""


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


def location_key(location: str) -> str:
    """Normalise a backend location so the inventory and the lock agree on it.

    The default inventory names a local target by its directory and `--live`
    by its `file://` URI; both become the resolved path. Other URIs are
    returned unchanged.
    """
    if "://" not in location:
        return str(Path(location).resolve())
    parsed = urlparse(location)
    if parsed.scheme == "file":
        return str(Path(parsed.netloc + parsed.path).resolve())
    return location


def lock_identities(path: Path) -> dict[tuple[str, str], LockEntry] | None:
    """Map each (target location, storage key) `ditto.lock` records to its entry.

    A stored name shortens and replaces characters of the test name and key, so
    the lock is where their exact values are. Keyed by target as well as name:
    the same name under another target is a different snapshot. Locations are
    normalised with `location_key`. Returns `None` when no readable lock
    governs `path`; the inventory itself warns about an unreadable one.
    """
    lock_path = _find_lock(path)
    if lock_path is None:
        return None
    try:
        lock = read_lockfile(lock_path)
    except DittoLockFileError:
        return None
    if lock is None:
        return None
    rootdir = lock_path.parent
    identities: dict[tuple[str, str], LockEntry] = {}
    for target_id, target in lock.targets.items():
        location = (
            str(_file_target_path(target_id, rootdir))
            if target.scheme == "file"
            else location_key(target_id)
        )
        for entry in target.entries:
            identities[(location, storage_key(entry, target.scheme))] = entry
    return identities


def _is_within(resolved: Path, base: Path) -> bool:
    """Return whether `resolved` is `base` itself or nested under it."""
    return resolved == base or base in resolved.parents


def _nodeid_under(nodeid: str, rootdir: Path, base: Path) -> bool:
    """Return whether a lock entry's test file falls under `base` (the PATH)."""
    file_part = nodeid.split("::", 1)[0]
    resolved = (rootdir / file_part).resolve()
    return _is_within(resolved, base)


def _file_target_path(target_id: str, rootdir: Path) -> Path:
    """Resolve a portable lock target id to its local filesystem path."""
    parsed = urlparse(target_id)
    if parsed.scheme == "file":
        return Path(parsed.netloc + parsed.path).resolve()
    return (rootdir / target_id).resolve()


def _local_ditto_dirs(
    path: Path, lock: LockFile | None, rootdir: Path | None
) -> dict[Path, set[str] | None]:
    """Locate every `.ditto` directory to inventory under `path`.

    Walks `path` for `.ditto` directories (including `path` itself when it is
    one) and adds any `file`-scheme target directory recorded in `lock` whose
    directory or owning tests fall under `path` (deduplicated by resolved path,
    insertion-ordered for stable output).

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
    dict[Path, set[str] | None]
        Resolved directories in discovery order, mapped to the storage keys
        in scope. `None` means the whole directory was selected, including
        untracked files. A discovered symlink selects its whole destination.
    """
    base = path.resolve()
    dirs: dict[Path, set[str] | None] = dict.fromkeys(
        d.resolve()
        for d in (base, *base.rglob(".ditto"))
        if d.name == ".ditto" and d.is_dir()
    )
    if lock is not None and rootdir is not None:
        for target_id, target in lock.targets.items():
            if target.scheme != "file":
                continue
            resolved = _file_target_path(target_id, rootdir)
            if not resolved.is_dir():
                continue
            if _is_within(resolved, base):
                dirs[resolved] = None
            if resolved in dirs and dirs[resolved] is None:
                continue
            keys = {
                storage_key(entry, target.scheme)
                for entry in target.entries
                if _nodeid_under(entry.nodeid, rootdir, base)
            }
            if keys:
                selected = dirs.setdefault(resolved, set())
                if selected is not None:
                    selected.update(keys)
    return dirs


def _read_ditto_dir(directory: Path) -> list[ManifestEntry]:
    """Stat each file in `directory` into a manifest entry (real size + mtime).

    Files that vanish between listing and stat are skipped rather than raising.
    Other filesystem errors fail the inventory rather than hiding snapshots.
    """
    entries: list[ManifestEntry] = []
    try:
        children = sorted(directory.iterdir())
    except OSError as exc:
        raise InventoryError(
            f"Could not read snapshot directory {directory}: {exc}"
        ) from exc

    for child in children:
        try:
            child_stat = child.stat()
        except FileNotFoundError:
            continue  # vanished between listing and stat (e.g. concurrent prune)
        except OSError as exc:
            raise InventoryError(f"Could not inspect snapshot {child}: {exc}") from exc
        if not stat.S_ISREG(child_stat.st_mode):
            continue
        entries.append(
            ManifestEntry(
                storage_key=child.name,
                size_bytes=child_stat.st_size,
                modified=child_stat.st_mtime,
            )
        )
    return entries


def _walk_local(path: Path, lock: LockFile | None, rootdir: Path | None) -> Manifest:
    """Inventory local `file` snapshots from disk under `path`.

    One `BackendManifest` per non-empty `.ditto/` directory located by
    `_local_ditto_dirs`; each file is stat'd for real size and mtime.

    Directly selected directories include untracked files, even when discovered
    through a symlink. Targets selected only by owning test keep only those
    tests' lock entries, using the same per-entry rule as `_lock_remote`.
    """
    backends: Manifest = []
    for directory, in_scope in _local_ditto_dirs(path, lock, rootdir).items():
        entries = _read_ditto_dir(directory)
        if in_scope is not None:
            entries = [entry for entry in entries if entry.storage_key in in_scope]
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


def _build_credential_free_inventory(path: Path) -> Manifest:
    """Assemble the inventory for `path` without importing tests.

    Reads local `file` snapshots from the filesystem (real size and mtime,
    including on-disk orphans) and remote (non-`file`) snapshots from the
    committed `ditto.lock` (declared entries; size and mtime unknown). A
    missing lock yields a local-only inventory; a corrupt lock warns
    (`DittoWarning`) and degrades to local-only rather than failing.
    """
    lock_path = _find_lock(path)
    rootdir = lock_path.parent if lock_path is not None else None
    lock: LockFile | None = None
    if lock_path is not None:
        try:
            lock = read_lockfile(lock_path)
        except DittoLockFileError as exc:
            warnings.warn(
                f"{LOCKFILE_NAME} is unreadable ({exc}); showing local snapshots "
                "only; use --live for the full inventory.",
                category=DittoWarning,
                stacklevel=2,
            )
            lock = None
    return _walk_local(path, lock, rootdir) + _lock_remote(lock, path, rootdir)


def build_inventory(path: Path, *, live: bool) -> Manifest:
    """Assemble the snapshot inventory for `path`.

    By default reads credential-free from the filesystem (local) and `ditto.lock`
    (remote). With `live=True`, runs the pytest introspection pass for
    authoritative physical state across every target.
    """
    if live:
        return run_introspect(path)
    return _build_credential_free_inventory(path)
