from __future__ import annotations

import pytest

from tests.integration.support.cli import (
    assert_lock_verify_and_recover,
    assert_record_replay_inventory,
)

pytestmark = [pytest.mark.integration]


def test_local_backend_record_replay_and_inventory(project_workspace) -> None:
    workspace = project_workspace("local", "record-replay")
    assert_record_replay_inventory(
        workspace,
        env={},
        list_tokens=("scenario_suite", "alpha", "beta", "json"),
        status_tokens=("ditto status", "Total snapshots", "json"),
        stats_tokens=("ditto stats", "TOTAL", "json×2"),
    )


def test_local_backend_lock_verify_and_recover(project_workspace) -> None:
    workspace = project_workspace("local", "lock-verify")
    assert_lock_verify_and_recover(
        workspace,
        env={},
        missing_fragment="test_alpha",
    )
