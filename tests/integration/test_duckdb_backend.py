from __future__ import annotations

import pytest

from tests.integration.support.cli import (
    assert_lock_verify_and_recover,
    assert_record_replay_inventory,
)

pytestmark = [pytest.mark.integration]


def test_duckdb_backend_record_replay_and_inventory(project_workspace) -> None:
    workspace = project_workspace("duckdb", "record-replay")
    env = {
        "DITTO_DUCKDB_TARGET": (
            f"duckdb://{(workspace.project / '.standalone-snapshots.duckdb').as_posix()}"
        ),
    }
    assert_record_replay_inventory(
        workspace,
        env=env,
        list_tokens=("scenario_suite", "alpha", "beta", "json"),
        status_tokens=("ditto status", "Total snapshots", "json"),
        stats_tokens=("ditto stats", "TOTAL", "json×2"),
    )


def test_duckdb_backend_lock_verify_and_recover(project_workspace) -> None:
    workspace = project_workspace("duckdb", "lock-verify")
    env = {
        "DITTO_DUCKDB_TARGET": (
            f"duckdb://{(workspace.project / '.standalone-snapshots.duckdb').as_posix()}"
        ),
    }
    assert_lock_verify_and_recover(
        workspace,
        env=env,
        missing_fragment="test_alpha",
    )
