"""The private handoff from a pytest run to the standalone `ditto` command.

Standalone `ditto run/update/lock/prune` runs pytest with `--ditto-handoff=PATH`.
pytest writes what it did to snapshots and the lock to PATH, and `ditto`
reads it back to print one report. It is private to the two and versioned, so
a field is added when something first reads it.

Nothing here holds an error message: a backend's can carry credentials, and
pytest has already printed it. Targets never carry credentials, since a
target URI with one is refused before any snapshot is taken.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import msgspec

from ._atomic import write_atomically


__all__ = (
    "HANDOFF_VERSION",
    "Handoff",
    "LockOutcome",
    "Outcome",
    "SnapshotRef",
    "decode_handoff",
    "encode_handoff",
    "read_handoff",
    "write_handoff",
)


HANDOFF_VERSION = 1


class SnapshotRef(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    """A stored snapshot: where it is, and whose it is when that's known.

    The identity is None for a prune orphan, whose owner the lock doesn't
    record; it is never guessed from the storage key.
    """

    target: str
    storage_key: str
    nodeid: str | None = None
    key: str | None = None
    recorder: str | None = None


class Outcome(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    """What a run did, or would do, to one stored snapshot."""

    snapshot: SnapshotRef
    outcome: Literal[
        "created",
        "rewritten",
        "write_failed",
        "deleted",
        "delete_failed",
        "would_delete",
    ]


class LockOutcome(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    """What a run did to `ditto.lock`, counted in lock entries."""

    status: Literal["unchanged", "written", "failed", "refused"] = "unchanged"
    added: int = 0
    removed: int = 0


class Handoff(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    version: int
    outcomes: tuple[Outcome, ...] = ()
    lock: LockOutcome = LockOutcome()


def encode_handoff(handoff: Handoff) -> bytes:
    return msgspec.json.encode(handoff)


def decode_handoff(data: bytes) -> Handoff:
    """Decode a handoff; raise ValueError for any other version or shape."""
    handoff = msgspec.json.decode(data, type=Handoff)
    if handoff.version != HANDOFF_VERSION:
        raise ValueError(f"unsupported handoff version {handoff.version}")
    return handoff


def read_handoff(path: Path) -> Handoff:
    return decode_handoff(path.read_bytes())


def write_handoff(path: Path, handoff: Handoff) -> None:
    """Write `handoff` atomically, so a reader never sees half of one."""
    write_atomically(path, encode_handoff(handoff))
