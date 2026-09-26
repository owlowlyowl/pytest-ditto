import pytest

from ditto.plugin._lock import LockAction, choose_lock_action
from ditto.plugin._options import PruneMode, RunOptions
from ditto.snapshot import SnapshotMode


def _options(
    snapshot_mode: SnapshotMode = SnapshotMode.RECORD,
    rebuild_lock: bool = False,
    prune: PruneMode = PruneMode.OFF,
) -> RunOptions:
    return RunOptions(
        snapshot_mode=snapshot_mode,
        rebuild_lock=rebuild_lock,
        prune=prune,
        introspect_path="",
    )


@pytest.mark.parametrize("authoritative", [True, False])
def test_appends_when_recording_without_pruning(authoritative: bool) -> None:
    """A plain run appends its new entries, whether or not it is authoritative."""
    actual = choose_lock_action(_options(), authoritative)

    assert actual is LockAction.APPEND


def test_rebuilds_when_lock_rebuild_is_requested_on_authoritative_run() -> None:
    """`--ditto-lock` on a full, passing run rebuilds the lock."""
    actual = choose_lock_action(_options(rebuild_lock=True), authoritative=True)

    assert actual is LockAction.REBUILD


def test_refuses_when_lock_rebuild_is_requested_on_partial_run() -> None:
    """`--ditto-lock` on a run that cannot rebuild the lock is refused."""
    actual = choose_lock_action(_options(rebuild_lock=True), authoritative=False)

    assert actual is LockAction.REFUSE


def test_rebuilds_when_lock_rebuild_is_combined_with_pruning() -> None:
    """An explicit lock rebuild takes precedence over keeping the lock for a prune."""
    options = _options(rebuild_lock=True, prune=PruneMode.DELETE)

    actual = choose_lock_action(options, authoritative=True)

    assert actual is LockAction.REBUILD


def test_rebuilds_when_updating_on_authoritative_run() -> None:
    """`--ditto-update` on a full, passing run rebuilds the lock."""
    options = _options(snapshot_mode=SnapshotMode.UPDATE)

    actual = choose_lock_action(options, authoritative=True)

    assert actual is LockAction.REBUILD


def test_appends_when_updating_on_partial_run() -> None:
    """`--ditto-update` on a partial run only appends, never rebuilds."""
    options = _options(snapshot_mode=SnapshotMode.UPDATE)

    actual = choose_lock_action(options, authoritative=False)

    assert actual is LockAction.APPEND


@pytest.mark.parametrize("prune", [PruneMode.DELETE, PruneMode.DRY_RUN])
def test_keeps_lock_when_pruning(prune: PruneMode) -> None:
    """A prune run leaves the lock unchanged, so new snapshots stay unsynced."""
    actual = choose_lock_action(_options(prune=prune), authoritative=True)

    assert actual is LockAction.KEEP


def test_keeps_lock_when_updating_and_pruning_on_partial_run() -> None:
    """A partial update run that also prunes leaves the lock unchanged."""
    options = _options(snapshot_mode=SnapshotMode.UPDATE, prune=PruneMode.DELETE)

    actual = choose_lock_action(options, authoritative=False)

    assert actual is LockAction.KEEP
