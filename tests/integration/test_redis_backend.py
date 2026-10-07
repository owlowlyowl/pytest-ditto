from __future__ import annotations

import pytest

from tests.integration.support.cli import (
    assert_changed_value_fails_until_updated,
    assert_lock_verify_and_recover,
    assert_prune_respects_shared_targets,
    assert_record_replay_inventory,
)

pytestmark = [pytest.mark.integration, pytest.mark.docker]


def test_redis_backend_record_replay_and_inventory(
    project_workspace, redis_service
) -> None:
    workspace = project_workspace("redis", "record-replay")
    env = {"DITTO_REDIS_TARGET": redis_service.target}
    assert_record_replay_inventory(workspace, env=env)


def test_redis_backend_lock_verify_and_recover(
    project_workspace, redis_service
) -> None:
    workspace = project_workspace("redis", "lock-verify")
    env = {"DITTO_REDIS_TARGET": redis_service.target}
    assert_lock_verify_and_recover(workspace, env=env)


def test_redis_backend_changed_value_fails_until_updated(
    project_workspace, redis_service
) -> None:
    workspace = project_workspace("redis", "mismatch")
    env = {"DITTO_REDIS_TARGET": redis_service.target}
    assert_changed_value_fails_until_updated(workspace, env=env)


def test_redis_backend_prune_respects_shared_targets(
    project_workspace, redis_service
) -> None:
    workspace = project_workspace("redis", "prune")
    env = {"DITTO_REDIS_TARGET": redis_service.target}
    assert_prune_respects_shared_targets(workspace, env=env, shared=True)
