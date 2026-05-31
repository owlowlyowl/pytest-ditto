from __future__ import annotations

import pytest

from tests.integration.support.cli import (
    assert_lock_verify_and_recover,
    assert_record_replay_inventory,
)

pytestmark = [pytest.mark.integration, pytest.mark.docker]


def test_postgresql_backend_record_replay_and_inventory(
    project_workspace,
    postgres_service,
) -> None:
    workspace = project_workspace("postgres", "record-replay")
    env = {
        "DITTO_POSTGRES_TARGET": postgres_service.target,
        "DITTO_POSTGRES_USER": postgres_service.user,
        "DITTO_POSTGRES_PASSWORD": postgres_service.password,
    }
    assert_record_replay_inventory(
        workspace,
        env=env,
        list_tokens=("scenario_suite", "alpha", "beta", "json"),
        status_tokens=("ditto status", "Total snapshots", "json"),
        stats_tokens=("ditto stats", "TOTAL", "json×2"),
    )


def test_postgresql_backend_lock_verify_and_recover(
    project_workspace,
    postgres_service,
) -> None:
    workspace = project_workspace("postgres", "lock-verify")
    env = {
        "DITTO_POSTGRES_TARGET": postgres_service.target,
        "DITTO_POSTGRES_USER": postgres_service.user,
        "DITTO_POSTGRES_PASSWORD": postgres_service.password,
    }
    assert_lock_verify_and_recover(
        workspace,
        env=env,
        missing_fragment="test_alpha",
    )
