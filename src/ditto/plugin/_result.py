"""Collect the private standalone handoff independently of presentation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ditto._lockfile import LOCKFILE_NAME, LockFile, read_lockfile
from ditto._results import (
    RESULT_VERSION,
    Coverage,
    Identity,
    LockDelta,
    LockResult,
    OperationResult,
    TestResult,
    safe_location,
    write_result,
)

from ._lock import is_authoritative_run
from ._options import run_options, xdist_is_distributing
from ._session import session_state


def capture_lock_before(session: pytest.Session) -> None:
    state = session_state(session.config)
    try:
        state.lock_before = read_lockfile(session.config.rootpath / LOCKFILE_NAME)
    except Exception as exc:
        state.lock_before_error = type(exc).__name__


def _entries(lock: LockFile | None) -> set[tuple[str, str, str, str]]:
    return (
        {
            (target, entry.nodeid, entry.key, entry.recorder)
            for target, group in lock.targets.items()
            for entry in group.entries
        }
        if lock
        else set()
    )


def _delta(items: set[tuple[str, str, str, str]]) -> tuple[LockDelta, ...]:
    return tuple(
        LockDelta(safe_location(target), Identity(nodeid, key, recorder))
        for target, nodeid, key, recorder in sorted(items)
    )


def collect_result(session: pytest.Session) -> OperationResult:
    state = session_state(session.config)
    status = (
        state.result_exit_code
        if state.result_exit_code is not None
        else int(session.exitstatus)
    )
    lock = LockResult()
    try:
        after = read_lockfile(session.config.rootpath / LOCKFILE_NAME)
    except Exception as exc:
        lock = LockResult(reason=f"{type(exc).__name__} reading final lock")
    else:
        if state.lock_before_error:
            lock = LockResult(reason="Initial lock unreadable; deltas unknown")
        else:
            before_entries, after_entries = _entries(state.lock_before), _entries(after)
            lock_status = (
                "failed"
                if state.lock_failure
                else "unchanged"
                if after == state.lock_before
                else "written"
            )
            lock = LockResult(
                lock_status,
                _delta(after_entries - before_entries),
                _delta(before_entries - after_entries),
                state.lock_failure,
            )
    unsupported = xdist_is_distributing(session.config)
    coverage = tuple(state.coverage) + tuple(
        Coverage(
            safe_location(target),
            "runtime",
            "unchecked",
            "Runtime target resolved; physical inventory not enumerated",
        )
        for target in sorted(state.tracker.target_backends)
        if not any(c.target == safe_location(target) for c in state.coverage)
    )
    if state.lock_before:
        seen_targets = {c.target for c in coverage}
        coverage += tuple(
            Coverage(
                safe_location(target),
                "lock",
                "unchecked",
                "Historical target not resolved or inspected",
            )
            for target in sorted(state.lock_before.targets)
            if safe_location(target) not in seen_targets
        )
    # A failed/interrupted pass cannot establish complete ownership discovery.
    complete = status == 0 and not state.collection.uncollected
    full = is_authoritative_run(session, status) and not (
        state.collection.deselected
        or getattr(session.config.option, "collectonly", False)
        or getattr(session.config.option, "setuponly", False)
    )
    return OperationResult(
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
        "unsupported" if unsupported else "complete" if complete else "incomplete",
        "Snapshot aggregation under pytest-xdist is unsupported"
        if unsupported
        else "Run failed, interrupted, or has unexamined collection"
        if not complete
        else None,
        "unknown"
        if unsupported
        else "full"
        if full
        else "selected"
        if status == 0
        else "unknown",
    )


def write_session_result(session: pytest.Session) -> None:
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
