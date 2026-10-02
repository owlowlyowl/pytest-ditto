"""Collect the private standalone handoff independently of presentation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ditto._lockfile import LOCKFILE_NAME, read_lockfile
from ditto._result_io import write_result
from ditto._result_policy import (
    classify,
    lock_result,
    redact_targets,
    target_coverage,
)
from ditto._results import (
    RESULT_VERSION,
    Activity,
    Identity,
    Metadata,
    ObjectRef,
    OperationResult,
    TestResult,
)
from ditto.snapshot import SnapshotEvent

from ._collector import ResultCollector
from ._lock import is_authoritative_run
from ._options import xdist_is_distributing
from ._session import session_state


__all__ = ("start_collector", "write_session_result")


def start_collector(session: pytest.Session, path: Path) -> ResultCollector:
    """Begin collecting for `path`: note the lock now, and record snapshot calls."""
    results = ResultCollector(path)
    try:
        results.lock_before = read_lockfile(session.config.rootpath / LOCKFILE_NAME)
    except Exception as exc:
        results.lock_before_error = type(exc).__name__
    session_state(session.config).tracker.events = []
    return results


def snapshot_activity(event: SnapshotEvent) -> Activity:
    """Describe one snapshot call; a failure's reason names only the error type."""
    ref = ObjectRef(
        event.target,
        event.storage_key,
        Identity(event.key.nodeid, event.key.key, event.key.identifier),
    )
    match event.outcome, event.phase:
        case "failed", "write":
            reason = f"{event.error} during snapshot write; completion unconfirmed"
        case "failed", "read":
            reason = f"{event.error} during snapshot read"
        case "missing", _:
            reason = "Referenced object absent"
        case _:
            reason = None
    metadata = (
        Metadata(size_bytes=event.size, source="runtime")
        if event.size is not None
        else Metadata()
    )
    return Activity(ref, event.outcome, event.phase, reason, metadata)


def collect_result(
    session: pytest.Session, results: ResultCollector
) -> OperationResult:
    """Freeze the session's evidence into an unredacted result."""
    state = session_state(session.config)
    status = int(
        results.exit_override
        if results.exit_override is not None
        else session.exitstatus
    )
    after = None
    final_error = None
    try:
        after = read_lockfile(session.config.rootpath / LOCKFILE_NAME)
    except Exception as exc:
        final_error = type(exc).__name__
    full = is_authoritative_run(session, status) and not (
        state.collection.deselected
        or getattr(session.config.option, "collectonly", False)
        or getattr(session.config.option, "setuponly", False)
    )
    completeness, scope_kind, reason = classify(
        status,
        full=full,
        uncollected=bool(state.collection.uncollected),
        distributing=xdist_is_distributing(session.config),
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
            tuple(results.phases),
        ),
        tuple(snapshot_activity(event) for event in state.tracker.events or ())
        + tuple(results.activity),
        target_coverage(
            results.coverage,
            state.tracker.target_backends.keys(),
            results.lock_before.targets.keys() if results.lock_before else frozenset(),
        ),
        tuple(results.checks),
        lock_result(
            results.lock_before,
            after,
            results.lock_before_error,
            final_error,
            results.lock_problem,
        ),
        completeness,
        reason,
        scope_kind,
    )


def write_session_result(session: pytest.Session, results: ResultCollector) -> None:
    """Publish the redacted handoff; never let a failure mask pytest's outcome."""
    try:
        write_result(results.path, redact_targets(collect_result(session, results)))
    except Exception as exc:
        # Never serialize arbitrary backend messages or mask pytest's outcome.
        print(
            f"ditto: standalone result unavailable ({type(exc).__name__}).",
            file=sys.stderr,
        )
