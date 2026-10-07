from __future__ import annotations

import pytest

from tests.integration.harness.backend_state import capture_backend
from tests.integration.harness.cli import run_ditto
from tests.integration.harness.output import panel_lines, table_rows
from tests.integration.harness.project import ALPHA_NODEID, BETA_NODEID
from tests.integration.harness.workspace import RecordedState, Workspace

pytestmark = pytest.mark.integration


def test_lists_exact_snapshot_identities_when_inventory_is_requested(
    workspace: Workspace,
    recorded_state: RecordedState,
    inventory_args: tuple[str, ...],
    snapshot_sizes: tuple[str, str],
    snapshot_dates: tuple[str, str],
) -> None:
    """Inventory lists each test, key, recorder, size and modification date."""
    listed = run_ditto(workspace, "02-list", "list", *inventory_args)

    assert listed.returncode == 0
    # Redis SCAN order varies; sorting preserves duplicate rows for comparison.
    actual = sorted(table_rows(listed.stdout))
    expected = [
        (ALPHA_NODEID, "alpha", "json", snapshot_sizes[0], snapshot_dates[0]),
        (BETA_NODEID, "beta", "json", snapshot_sizes[1], snapshot_dates[1]),
    ]
    assert actual == expected
    assert (
        capture_backend(workspace, "02-backend-after-list") == recorded_state.snapshots
    )
    assert (workspace.project / "ditto.lock").read_bytes() == recorded_state.lock


def test_reports_exact_totals_when_status_is_requested(
    workspace: Workspace,
    recorded_state: RecordedState,
    inventory_args: tuple[str, ...],
    total_size: str,
) -> None:
    """Status counts both snapshots with sizes appropriate to the inventory mode."""
    status = run_ditto(workspace, "02-status", "status", *inventory_args)

    assert status.returncode == 0
    actual = panel_lines(status.stdout)
    assert "Total snapshots 2" in actual
    assert f"Total size {total_size}" in actual
    assert f"json 2 {total_size}" in actual
    assert (
        capture_backend(workspace, "02-backend-after-status")
        == recorded_state.snapshots
    )
    assert (workspace.project / "ditto.lock").read_bytes() == recorded_state.lock


def test_reports_exact_target_usage_when_stats_are_requested(
    workspace: Workspace,
    recorded_state: RecordedState,
    inventory_args: tuple[str, ...],
    total_size: str,
    inventory_location: str,
) -> None:
    """Stats reports the exact target usage and aggregate footer."""
    stats = run_ditto(workspace, "02-stats", "stats", *inventory_args)

    assert stats.returncode == 0
    actual = table_rows(stats.stdout)
    expected = [
        (inventory_location, "2", total_size, "json×2"),
        ("TOTAL", "2", total_size, ""),
    ]
    assert actual == expected
    assert (
        capture_backend(workspace, "02-backend-after-stats") == recorded_state.snapshots
    )
    assert (workspace.project / "ditto.lock").read_bytes() == recorded_state.lock


def test_lists_only_selected_snapshot_when_exact_test_id_is_given(
    workspace: Workspace, recorded_state: RecordedState
) -> None:
    """An exact node ID selects its snapshot and excludes the other test."""
    listed = run_ditto(workspace, "02-list-alpha", "list", "--test", ALPHA_NODEID)

    assert listed.returncode == 0
    actual = [row[:3] for row in table_rows(listed.stdout)]
    expected = [(ALPHA_NODEID, "alpha", "json")]
    assert actual == expected
    assert (
        capture_backend(workspace, "02-backend-after-selection")
        == recorded_state.snapshots
    )
    assert (workspace.project / "ditto.lock").read_bytes() == recorded_state.lock
