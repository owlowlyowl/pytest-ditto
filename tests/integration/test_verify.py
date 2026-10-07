from __future__ import annotations

import pytest

from tests.integration.harness.backend_state import (
    capture_backend,
    remove_backend_entry,
)
from tests.integration.harness.cli import run_ditto
from tests.integration.harness.project import (
    ALPHA_NODEID,
    logical_storage_key,
    snapshot_key_for,
)
from tests.integration.harness.workspace import RecordedState, Workspace

pytestmark = pytest.mark.integration


def test_reports_no_drift_when_storage_matches_lock(
    workspace: Workspace, recorded_state: RecordedState
) -> None:
    """A clean verify checks the recorded target without changing any state."""
    verified = run_ditto(workspace, "02-verify", "verify")

    assert verified.returncode == 0
    assert (
        f"ditto verify: no drift in 1 target: {workspace.target_id}" in verified.stdout
    )
    assert (
        capture_backend(workspace, "02-backend-after-verify")
        == recorded_state.snapshots
    )
    assert (workspace.project / "ditto.lock").read_bytes() == recorded_state.lock


def test_reports_missing_snapshot_when_storage_entry_is_deleted(
    workspace: Workspace, recorded_state: RecordedState
) -> None:
    """Verify identifies a deleted snapshot while leaving it absent."""
    alpha_key = snapshot_key_for(recorded_state.snapshots, "test_alpha")
    remove_backend_entry(workspace, alpha_key)
    expected = dict(recorded_state.snapshots)
    del expected[alpha_key]
    assert capture_backend(workspace, "02-backend-after-delete") == expected

    verified = run_ditto(workspace, "03-verify-missing", "verify")

    assert verified.returncode == 1
    assert f"  {workspace.target_id}:" in verified.stdout
    assert "missing (recorded in lock, absent from backend):" in verified.stdout
    assert f"{ALPHA_NODEID}  alpha  {logical_storage_key(alpha_key)}" in verified.stdout
    actual = capture_backend(workspace, "03-backend-after-verify")
    assert actual == expected
    assert (workspace.project / "ditto.lock").read_bytes() == recorded_state.lock


def test_restores_missing_snapshot_when_updated(
    workspace: Workspace, recorded_state: RecordedState
) -> None:
    """Update restores a deleted snapshot so the target verifies cleanly again."""
    alpha_key = snapshot_key_for(recorded_state.snapshots, "test_alpha")
    remove_backend_entry(workspace, alpha_key)

    updated = run_ditto(workspace, "02-update-missing", "update")
    verified = run_ditto(workspace, "03-verify-recovered", "verify")

    assert updated.returncode == 0
    assert verified.returncode == 0
    assert (
        f"ditto verify: no drift in 1 target: {workspace.target_id}" in verified.stdout
    )
    assert (
        capture_backend(workspace, "03-recovered-backend") == recorded_state.snapshots
    )
    assert (workspace.project / "ditto.lock").read_bytes() == recorded_state.lock


def test_reports_orphan_when_snapshot_is_absent_from_lock(
    workspace: Workspace, orphaned_state: RecordedState
) -> None:
    """Verify identifies the removed test's snapshot without changing storage."""
    beta_key = snapshot_key_for(orphaned_state.snapshots, "test_beta")

    verified = run_ditto(workspace, "03-verify-orphan", "verify")

    assert verified.returncode == 1
    assert f"  {workspace.target_id}:" in verified.stdout
    assert "orphan (in backend, not in lock):" in verified.stdout
    assert logical_storage_key(beta_key) in verified.stdout
    assert (
        capture_backend(workspace, "03-backend-after-verify")
        == orphaned_state.snapshots
    )
    assert (workspace.project / "ditto.lock").read_bytes() == orphaned_state.lock
