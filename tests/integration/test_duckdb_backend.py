from __future__ import annotations

import pytest

from tests.integration.support.cli import (
    assert_changed_value_fails_until_updated,
    assert_lock_verify_and_recover,
    assert_prune_respects_shared_targets,
    assert_record_replay_inventory,
)

pytestmark = [pytest.mark.integration]


def test_duckdb_backend_record_replay_and_inventory(project_workspace) -> None:
    workspace = project_workspace("duckdb", "record-replay")
    target = workspace.project / ".standalone-snapshots.duckdb"
    env = {"DITTO_DUCKDB_TARGET": f"duckdb://{target.as_posix()}"}
    assert_record_replay_inventory(workspace, env=env)


def test_duckdb_backend_lock_verify_and_recover(project_workspace) -> None:
    workspace = project_workspace("duckdb", "lock-verify")
    target = workspace.project / ".standalone-snapshots.duckdb"
    env = {"DITTO_DUCKDB_TARGET": f"duckdb://{target.as_posix()}"}
    assert_lock_verify_and_recover(workspace, env=env)


def test_duckdb_backend_changed_value_fails_until_updated(project_workspace) -> None:
    workspace = project_workspace("duckdb", "mismatch")
    target = workspace.project / ".standalone-snapshots.duckdb"
    env = {"DITTO_DUCKDB_TARGET": f"duckdb://{target.as_posix()}"}
    assert_changed_value_fails_until_updated(workspace, env=env)


def test_duckdb_backend_prune_respects_shared_targets(project_workspace) -> None:
    workspace = project_workspace("duckdb", "prune")
    target = workspace.project / ".standalone-snapshots.duckdb"
    env = {"DITTO_DUCKDB_TARGET": f"duckdb://{target.as_posix()}"}
    assert_prune_respects_shared_targets(workspace, env=env, shared=True)
