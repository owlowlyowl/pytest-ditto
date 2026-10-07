from __future__ import annotations

import pytest

from tests.integration.harness.backend_state import capture_backend
from tests.integration.harness.cli import run_ditto
from tests.integration.harness.output import panel_lines
from tests.integration.harness.project import logical_storage_key, snapshot_key_for
from tests.integration.harness.workspace import RecordedState, Workspace

pytestmark = pytest.mark.integration

SHARED_BACKENDS = [
    pytest.param("duckdb", id="duckdb"),
    pytest.param("redis", id="redis", marks=pytest.mark.docker),
    pytest.param("postgres", id="postgres", marks=pytest.mark.docker),
]


@pytest.mark.parametrize("backend_name", SHARED_BACKENDS, indirect=True)
def test_preserves_shared_orphan_when_prune_check_is_requested(
    workspace: Workspace, orphaned_state: RecordedState
) -> None:
    """A prune check labels the remote orphan shared and preserves all state."""
    beta_key = snapshot_key_for(orphaned_state.snapshots, "test_beta")

    checked = run_ditto(workspace, "03-prune-check", "prune", "--check")

    assert checked.returncode == 0
    assert (
        "shared 1 (shared target: only pruned with --ditto-prune-shared)"
        in panel_lines(checked.stderr)
    )
    assert "would prune" not in checked.stderr
    assert workspace.target_id in checked.stderr
    assert logical_storage_key(beta_key) in checked.stderr
    assert (
        capture_backend(workspace, "03-backend-after-check") == orphaned_state.snapshots
    )
    assert (workspace.project / "ditto.lock").read_bytes() == orphaned_state.lock


@pytest.mark.parametrize("backend_name", SHARED_BACKENDS, indirect=True)
def test_refuses_to_delete_orphan_when_target_is_shared(
    workspace: Workspace, orphaned_state: RecordedState
) -> None:
    """Prune refuses a shared target unless shared deletion is requested."""
    pruned = run_ditto(workspace, "03-prune-without-shared", "prune")

    assert pruned.returncode == 1
    assert f"not deleting 1 snapshot(s) from {workspace.target_id!r}" in pruned.stdout
    assert (
        capture_backend(workspace, "03-backend-after-refusal")
        == orphaned_state.snapshots
    )
    assert (workspace.project / "ditto.lock").read_bytes() == orphaned_state.lock


@pytest.mark.parametrize("backend_name", SHARED_BACKENDS, indirect=True)
def test_deletes_only_orphan_when_shared_deletion_is_requested(
    workspace: Workspace, orphaned_state: RecordedState
) -> None:
    """Shared pruning deletes the orphan and preserves the remaining snapshot."""
    beta_key = snapshot_key_for(orphaned_state.snapshots, "test_beta")
    expected = dict(orphaned_state.snapshots)
    del expected[beta_key]

    pruned = run_ditto(workspace, "03-prune-shared", "prune", "--shared")

    assert pruned.returncode == 0
    assert "pruned 1" in panel_lines(pruned.stderr)
    actual = capture_backend(workspace, "03-backend-after-prune")
    assert actual == expected
    assert (workspace.project / "ditto.lock").read_bytes() == orphaned_state.lock

    verified = run_ditto(workspace, "04-verify-pruned", "verify")

    assert verified.returncode == 0
    assert (
        f"ditto verify: no drift in 1 target: {workspace.target_id}" in verified.stdout
    )
    assert capture_backend(workspace, "04-backend-after-verify") == expected


@pytest.mark.parametrize("backend_name", ["local"], indirect=True)
def test_preserves_local_orphan_when_prune_check_is_requested(
    workspace: Workspace, orphaned_state: RecordedState
) -> None:
    """A prune check identifies the local orphan without deleting anything."""
    beta_key = snapshot_key_for(orphaned_state.snapshots, "test_beta")

    checked = run_ditto(workspace, "03-prune-check", "prune", "--check")

    assert checked.returncode == 0
    assert "would prune 1 (use --ditto-prune to delete)" in panel_lines(checked.stderr)
    assert logical_storage_key(beta_key) in checked.stderr
    assert (
        capture_backend(workspace, "03-backend-after-check") == orphaned_state.snapshots
    )
    assert (workspace.project / "ditto.lock").read_bytes() == orphaned_state.lock


@pytest.mark.parametrize("backend_name", ["local"], indirect=True)
def test_deletes_only_orphan_when_target_is_checkout_local(
    workspace: Workspace, orphaned_state: RecordedState
) -> None:
    """Checkout-local pruning needs no shared flag and keeps the live snapshot."""
    beta_key = snapshot_key_for(orphaned_state.snapshots, "test_beta")
    expected = dict(orphaned_state.snapshots)
    del expected[beta_key]

    pruned = run_ditto(workspace, "03-prune-local", "prune")

    assert pruned.returncode == 0
    assert "pruned 1" in panel_lines(pruned.stderr)
    actual = capture_backend(workspace, "03-backend-after-prune")
    assert actual == expected
    assert (workspace.project / "ditto.lock").read_bytes() == orphaned_state.lock

    verified = run_ditto(workspace, "04-verify-pruned", "verify")

    assert verified.returncode == 0
    assert (
        f"ditto verify: no drift in 1 target: {workspace.target_id}" in verified.stdout
    )
    assert capture_backend(workspace, "04-backend-after-verify") == expected
