from __future__ import annotations

import pytest

from tests.integration.support.cli import (
    assert_changed_value_fails_until_updated,
    assert_lock_verify_and_recover,
    assert_prune_respects_shared_targets,
    assert_record_replay_inventory,
)

pytestmark = [pytest.mark.integration, pytest.mark.docker]


def test_postgres_backend_record_replay_and_inventory(
    project_workspace, postgres_service
) -> None:
    workspace = project_workspace("postgres", "record-replay")
    env = {
        "DITTO_POSTGRES_TARGET": postgres_service.target,
        "DITTO_POSTGRES_USER": postgres_service.user,
        "DITTO_POSTGRES_PASSWORD": postgres_service.password,
    }
    assert_record_replay_inventory(workspace, env=env)


def test_postgres_backend_lock_verify_and_recover(
    project_workspace, postgres_service
) -> None:
    workspace = project_workspace("postgres", "lock-verify")
    env = {
        "DITTO_POSTGRES_TARGET": postgres_service.target,
        "DITTO_POSTGRES_USER": postgres_service.user,
        "DITTO_POSTGRES_PASSWORD": postgres_service.password,
    }
    assert_lock_verify_and_recover(workspace, env=env)


def test_postgres_backend_changed_value_fails_until_updated(
    project_workspace, postgres_service
) -> None:
    workspace = project_workspace("postgres", "mismatch")
    env = {
        "DITTO_POSTGRES_TARGET": postgres_service.target,
        "DITTO_POSTGRES_USER": postgres_service.user,
        "DITTO_POSTGRES_PASSWORD": postgres_service.password,
    }
    assert_changed_value_fails_until_updated(workspace, env=env)


def test_postgres_backend_prune_respects_shared_targets(
    project_workspace, postgres_service
) -> None:
    workspace = project_workspace("postgres", "prune")
    env = {
        "DITTO_POSTGRES_TARGET": postgres_service.target,
        "DITTO_POSTGRES_USER": postgres_service.user,
        "DITTO_POSTGRES_PASSWORD": postgres_service.password,
    }
    assert_prune_respects_shared_targets(workspace, env=env, shared=True)
