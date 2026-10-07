from __future__ import annotations

import pytest

from tests.integration.harness.backend_state import capture_backend, load_lockfile
from tests.integration.harness.cli import run_ditto
from tests.integration.harness.project import ALPHA_NODEID, remove_test_beta
from tests.integration.harness.workspace import RecordedState, Workspace

pytestmark = pytest.mark.integration


def test_rebuilds_lock_for_remaining_tests_when_test_is_removed(
    workspace: Workspace, recorded_state: RecordedState
) -> None:
    """Rebuilding the lock drops the deleted test without deleting its snapshot."""
    remove_test_beta(workspace)

    rebuilt = run_ditto(workspace, "02-rebuild-lock", "lock")

    assert rebuilt.returncode == 0
    actual = load_lockfile(workspace.project)
    expected = {
        "version": 1,
        "targets": {
            workspace.target_id: {
                "scheme": workspace.scheme,
                "entries": [
                    {"nodeid": ALPHA_NODEID, "key": "alpha", "recorder": "json"},
                ],
            },
        },
    }
    assert actual == expected
    assert (
        capture_backend(workspace, "02-backend-after-lock") == recorded_state.snapshots
    )
