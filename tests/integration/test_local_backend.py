from __future__ import annotations

import pytest

from tests.integration.support.cli import (
    assert_changed_value_fails_until_updated,
    assert_lock_verify_and_recover,
    assert_prune_respects_shared_targets,
    assert_record_replay_inventory,
)

pytestmark = [pytest.mark.integration]


def test_local_backend_record_replay_and_inventory(project_workspace) -> None:
    workspace = project_workspace("local", "record-replay")
    env = {}
    assert_record_replay_inventory(workspace, env=env)


def test_local_backend_lock_verify_and_recover(project_workspace) -> None:
    workspace = project_workspace("local", "lock-verify")
    env = {}
    assert_lock_verify_and_recover(workspace, env=env)


def test_local_backend_changed_value_fails_until_updated(project_workspace) -> None:
    workspace = project_workspace("local", "mismatch")
    env = {}
    assert_changed_value_fails_until_updated(workspace, env=env)


def test_local_backend_prune_respects_shared_targets(project_workspace) -> None:
    workspace = project_workspace("local", "prune")
    env = {}
    assert_prune_respects_shared_targets(workspace, env=env, shared=False)
