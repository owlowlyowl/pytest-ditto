from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import msgspec

from ._atomic import write_atomically
from .exceptions import DittoLockFileError, DittoLockFileVersionError
from .snapshot import SnapshotKey, _flat_key, _remote_key

__all__ = (
    "LOCKFILE_VERSION",
    "LOCKFILE_NAME",
    "LockEntry",
    "LockTarget",
    "LockFile",
    "serialise",
    "deserialise",
    "read_lockfile",
    "write_lockfile",
    "portable_target_id",
    "split_nodeid",
    "storage_key",
    "merge_append",
)

LOCKFILE_VERSION = 1
LOCKFILE_NAME = "ditto.lock"


class LockEntry(msgspec.Struct, frozen=True, order=True):
    """One legitimate snapshot's identity.

    Carries the test `nodeid`, the snapshot `key`, and the recorder identifier.
    """

    nodeid: str
    key: str
    recorder: str


class LockTarget(msgspec.Struct, frozen=True):
    """All entries stored under one resolved target. `entries` is kept sorted."""

    scheme: str
    entries: tuple[LockEntry, ...]


class LockFile(msgspec.Struct, frozen=True):
    """The committed lock file: a version and a mapping of target id to `LockTarget`."""

    version: int
    targets: dict[str, LockTarget]


def _canonical(lock: LockFile) -> LockFile:
    """Return `lock` with targets and entries in sorted order for stable output."""
    return LockFile(
        version=lock.version,
        targets={
            target_id: LockTarget(
                scheme=target.scheme,
                entries=tuple(sorted(target.entries)),
            )
            for target_id, target in sorted(lock.targets.items())
        },
    )


def serialise(lock: LockFile) -> bytes:
    """Encode a `LockFile` to deterministic, indented JSON bytes."""
    return msgspec.json.format(msgspec.json.encode(_canonical(lock)), indent=2)


def deserialise(data: bytes) -> LockFile:
    """Decode lock-file JSON, validating shape and version."""
    lock = msgspec.json.decode(data, type=LockFile)
    if lock.version != LOCKFILE_VERSION:
        raise DittoLockFileVersionError(LOCKFILE_VERSION, lock.version)
    return lock


def read_lockfile(path: Path) -> LockFile | None:
    """Return the parsed lock file, `None` if absent, raising if present but corrupt.

    A `None` return means no lock file exists yet — callers should treat this as
    an empty lock (e.g. `lock = read_lockfile(p) or LockFile(version=LOCKFILE_VERSION,
    targets={})`).  A file that exists but cannot be parsed is always an error
    because it indicates corruption or a hand-edit mistake that should be fixed
    explicitly rather than silently overwritten.
    """
    if not path.exists():
        return None
    try:
        return deserialise(path.read_bytes())
    except DittoLockFileVersionError:
        raise
    except (msgspec.DecodeError, msgspec.ValidationError) as exc:
        raise DittoLockFileError(f"{path} is not valid ({exc})") from exc


def write_lockfile(path: Path, lock: LockFile) -> None:
    """Atomically write `lock` to `path`; see `write_atomically`."""
    write_atomically(path, serialise(lock))


def portable_target_id(canonical_uri: str, rootdir: Path) -> str:
    """Return a machine-independent target id.

    `file://` targets become the rootdir-relative posix path; other schemes are
    returned unchanged. A `file://` path outside `rootdir` (not portable) is
    returned as the full absolute URI, unchanged.
    """
    parsed = urlparse(canonical_uri)
    if parsed.scheme != "file":
        return canonical_uri
    path = Path(parsed.netloc + parsed.path)
    try:
        return path.relative_to(rootdir).as_posix()
    except ValueError:
        return canonical_uri


def split_nodeid(nodeid: str) -> tuple[str, str]:
    """Split a pytest nodeid into `(module_stem, group_name)`.

    `tests/test_api.py::TestX::test_foo` -> (`tests/test_api`, `TestX.test_foo`),
    matching `SnapshotKey.module` and `SnapshotKey.group_name`. The file's last
    extension is dropped whatever it is, so a doctest in `docs/guide.txt` has
    module `docs/guide`.

    This is the one derivation of a snapshot's identity from its test: the
    `snapshot` fixture builds keys with it, and lock, verify and prune rebuild
    the same keys from lock entries with it. Node ids always use forward
    slashes, so the result is the same on every platform.
    """
    path_part, _, rest = nodeid.partition("::")
    # A node id with no file path (a test outside the rootdir) has no module;
    # `PurePosixPath("")` is ".", which `with_suffix` rejects.
    module = PurePosixPath(path_part).with_suffix("").as_posix() if path_part else ""
    group = rest.replace("::", ".")
    return module, group


def storage_key(entry: LockEntry, scheme: str) -> str:
    """Derive the backend storage key for a lock entry.

    Reuses the live `SnapshotKey` logic: `file` schemes use the flat dotted key,
    all others use the slash-namespaced key.
    """
    module, group = split_nodeid(entry.nodeid)
    sk = SnapshotKey(module, group, entry.key, entry.recorder, entry.nodeid)
    return _flat_key(sk) if scheme == "file" else _remote_key(sk)


def merge_append(
    existing: LockFile | None,
    target_id: str,
    scheme: str,
    new_entries: Iterable[LockEntry],
) -> LockFile:
    """Return a new `LockFile` with `new_entries` unioned into `target_id`.

    Append-only: existing entries (in this and every other target) are preserved.
    Result entries are de-duplicated and sorted.
    """
    targets = dict(existing.targets) if existing is not None else {}
    current = targets.get(target_id)
    merged = set(current.entries) if current is not None else set()
    merged.update(new_entries)
    # A target's scheme is intrinsic to its id; preserve the existing one and only
    # fall back to the caller-supplied scheme when creating a new target.
    target_scheme = current.scheme if current is not None else scheme
    targets[target_id] = LockTarget(scheme=target_scheme, entries=tuple(sorted(merged)))
    return LockFile(version=LOCKFILE_VERSION, targets=targets)
