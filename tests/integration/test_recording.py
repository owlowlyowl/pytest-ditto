from __future__ import annotations

import json

import pytest

from tests.integration.harness.backend_state import capture_backend, load_lockfile
from tests.integration.harness.cli import run_ditto
from tests.integration.harness.output import panel_lines
from tests.integration.harness.project import (
    ALPHA_NODEID,
    BETA_NODEID,
    snapshot_key_for,
)
from tests.integration.harness.workspace import Workspace

pytestmark = pytest.mark.integration


def test_records_snapshots_when_storage_is_empty(
    workspace: Workspace, payload_backend: str
) -> None:
    """A first run stores both payloads under their test identities."""
    recorded = run_ditto(workspace, "01-record", "run")

    assert recorded.returncode == 0
    assert "2 created" in panel_lines(recorded.stderr)
    snapshots = capture_backend(workspace, "01-recorded-backend")
    assert len(snapshots) == 2
    actual = [
        json.loads(snapshots[snapshot_key_for(snapshots, "test_alpha")]),
        json.loads(snapshots[snapshot_key_for(snapshots, "test_beta")]),
    ]
    expected = [
        {"backend": payload_backend, "name": "alpha", "values": [1, 2, 3]},
        {"backend": payload_backend, "name": "beta", "values": [1, 2, 3]},
    ]
    assert actual == expected


def test_records_complete_lock_when_snapshots_are_created(workspace: Workspace) -> None:
    """The initial lock records the target, scheme and both complete identities."""
    recorded = run_ditto(workspace, "01-record", "run")

    assert recorded.returncode == 0
    actual = load_lockfile(workspace.project)
    expected = {
        "version": 1,
        "targets": {
            workspace.target_id: {
                "scheme": workspace.scheme,
                "entries": [
                    {"nodeid": ALPHA_NODEID, "key": "alpha", "recorder": "json"},
                    {"nodeid": BETA_NODEID, "key": "beta", "recorder": "json"},
                ],
            },
        },
    }
    assert actual == expected
