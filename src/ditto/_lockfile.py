from __future__ import annotations

import os
import tempfile
from pathlib import Path

import msgspec

from .exceptions import DittoLockFileError, DittoLockFileVersionError

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
)

LOCKFILE_VERSION = 1
LOCKFILE_NAME = "ditto.lock"


class LockEntry(msgspec.Struct, frozen=True, order=True):
    """One legitimate snapshot's identity: test `nodeid`, snapshot `key`, recorder ext."""

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
    """Atomically write `lock` to `path` (temp file in the same dir + os.replace)."""
    data = serialise(lock)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=".ditto.lock.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
