"""Collect the private standalone handoff independently of presentation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ditto._lockfile import LOCKFILE_NAME, read_lockfile
from ditto._result_io import write_result
from ditto._result_policy import (
    finalize_result,
    lock_result,
    target_coverage,
    unsupported_result,
)
from ditto._results import (
    RESULT_VERSION,
    OperationResult,
    TestResult,
)

from ._lock import is_authoritative_run
from ._options import run_options, xdist_is_distributing
from ._session import session_state


def capture_lock_before(session: pytest.Session) -> None:
    """Capture initial lock evidence in pytest's incremental session state."""
    state = session_state(session.config)
    try:
        state.lock_before = read_lockfile(session.config.rootpath / LOCKFILE_NAME)
    except Exception as exc:
        state.lock_before_error = type(exc).__name__


def collect_result(session: pytest.Session) -> OperationResult:
    """Freeze pytest observations and apply the independent result policies."""
    state = session_state(session.config)
    status = (
        state.result_exit_code
        if state.result_exit_code is not None
        else int(session.exitstatus)
    )
    after = None
    final_error = None
    try:
        after = read_lockfile(session.config.rootpath / LOCKFILE_NAME)
    except Exception as exc:
        final_error = type(exc).__name__
    lock = lock_result(
        state.lock_before,
        after,
        state.lock_before_error,
        final_error,
        state.lock_failure,
    )
    coverage = target_coverage(
        state.coverage,
        state.tracker.target_backends.keys(),
        state.lock_before.targets.keys() if state.lock_before else frozenset(),
    )
    full = is_authoritative_run(session, status) and not (
        state.collection.deselected
        or getattr(session.config.option, "collectonly", False)
        or getattr(session.config.option, "setuponly", False)
    )
    result = OperationResult(
        RESULT_VERSION,
        str(session.config.rootpath),
        TestResult(
            status,
            tuple(sorted(state.collection.collected)),
            tuple(sorted(state.collection.passed)),
            tuple(sorted(state.collection.uncollected)),
            tuple(sorted(state.collection.deselected)),
            tuple(state.test_phases),
        ),
        tuple(state.tracker.activity),
        coverage,
        tuple(state.checks),
        lock,
        scope_kind="full" if full else "selected",
    )
    if xdist_is_distributing(session.config):
        return unsupported_result(result)
    return finalize_result(result)


def write_session_result(session: pytest.Session) -> None:
    """Publish private evidence without replacing pytest's exit status."""
    path = run_options(session.config).result_path
    if not path:
        return
    try:
        write_result(Path(path), collect_result(session))
    except Exception as exc:
        # Never serialize arbitrary backend messages or mask pytest's outcome.
        print(
            f"ditto: standalone result unavailable ({type(exc).__name__}).",
            file=sys.stderr,
        )
