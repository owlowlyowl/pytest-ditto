from __future__ import annotations

import json

import pytest

from tests.integration.harness.backend_state import capture_backend
from tests.integration.harness.cli import run_ditto
from tests.integration.harness.output import panel_lines
from tests.integration.harness.project import (
    ALPHA_NODEID,
    BETA_NODEID,
    replace_values,
    snapshot_key_for,
)
from tests.integration.harness.workspace import RecordedState, Workspace

pytestmark = pytest.mark.integration


def test_replays_without_writing_when_values_are_unchanged(
    workspace: Workspace, recorded_state: RecordedState
) -> None:
    """Replaying unchanged values preserves stored bytes and the complete lock."""
    actual = run_ditto(workspace, "02-replay", "run")

    assert actual.returncode == 0
    assert "ditto snapshot report" not in actual.stderr
    assert (
        capture_backend(workspace, "02-backend-after-replay")
        == recorded_state.snapshots
    )
    assert (workspace.project / "ditto.lock").read_bytes() == recorded_state.lock


def test_replays_changed_values_when_update_has_replaced_snapshots(
    workspace: Workspace, recorded_state: RecordedState, payload_backend: str
) -> None:
    """Changed values fail without writes until update replaces their snapshots."""
    replace_values(workspace, [0, 1, 2, 3])

    changed = run_ditto(workspace, "02-changed-values", "run")

    assert changed.returncode == 1
    assert f"FAILED {ALPHA_NODEID} - AssertionError" in changed.stdout
    assert f"FAILED {BETA_NODEID} - AssertionError" in changed.stdout
    assert "ditto snapshot report" not in changed.stderr
    assert (
        capture_backend(workspace, "02-backend-after-failure")
        == recorded_state.snapshots
    )
    assert (workspace.project / "ditto.lock").read_bytes() == recorded_state.lock

    updated = run_ditto(workspace, "03-update", "update")

    assert updated.returncode == 0
    assert "2 rewritten" in panel_lines(updated.stderr)
    snapshots = capture_backend(workspace, "03-updated-backend")
    assert snapshots.keys() == recorded_state.snapshots.keys()
    actual = [
        json.loads(snapshots[snapshot_key_for(snapshots, "test_alpha")]),
        json.loads(snapshots[snapshot_key_for(snapshots, "test_beta")]),
    ]
    expected = [
        {"backend": payload_backend, "name": "alpha", "values": [0, 1, 2, 3]},
        {"backend": payload_backend, "name": "beta", "values": [0, 1, 2, 3]},
    ]
    assert actual == expected
    assert (workspace.project / "ditto.lock").read_bytes() == recorded_state.lock

    replayed = run_ditto(workspace, "04-replay-updated-values", "run")

    assert replayed.returncode == 0
    assert "ditto snapshot report" not in replayed.stderr
    assert capture_backend(workspace, "04-backend-after-replay") == snapshots
    assert (workspace.project / "ditto.lock").read_bytes() == recorded_state.lock
