from __future__ import annotations

import msgspec

from .exceptions import DittoLockFileVersionError

__all__ = (
    "LOCKFILE_VERSION",
    "LOCKFILE_NAME",
    "LockEntry",
    "LockTarget",
    "LockFile",
    "serialise",
    "deserialise",
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
