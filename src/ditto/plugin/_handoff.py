"""Build a run's handoff from what the session tracked."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from ditto._handoff import (
    HANDOFF_VERSION,
    Handoff,
    LockOutcome,
    Outcome,
    SnapshotRef,
)
from ditto._report import PrunedSnapshot
from ditto.snapshot import SnapshotWrite


__all__ = ("session_handoff",)


def _written(write: SnapshotWrite) -> Outcome:
    ref = SnapshotRef(
        write.target,
        write.storage_key,
        write.key.nodeid,
        write.key.key,
        write.key.identifier,
    )
    return Outcome(ref, write.outcome)


def _orphan(
    orphan: PrunedSnapshot,
    outcome: Literal["deleted", "delete_failed", "would_delete"],
) -> Outcome:
    # A prune orphan's owner isn't recorded, so its identity stays unknown.
    return Outcome(SnapshotRef(orphan.target_id, orphan.key), outcome)


def session_handoff(
    writes: Iterable[SnapshotWrite],
    deleted: Iterable[PrunedSnapshot],
    delete_failed: Iterable[PrunedSnapshot],
    would_delete: Iterable[PrunedSnapshot],
    lock: LockOutcome,
) -> Handoff:
    """Every snapshot written, then every orphan deleted, failed or proposed."""
    outcomes = (
        *(_written(w) for w in writes),
        *(_orphan(o, "deleted") for o in deleted),
        *(_orphan(o, "delete_failed") for o in delete_failed),
        *(_orphan(o, "would_delete") for o in would_delete),
    )
    return Handoff(HANDOFF_VERSION, outcomes, lock)
