from __future__ import annotations

import warnings

import pytest

from ditto._lockfile import LOCKFILE_NAME
from ditto._report import render_session_report
from ditto.exceptions import DittoWarning
from ditto.recorders import RECORDER_REGISTRY
from ditto.snapshot import SnapshotMode

from ._drift import delete_orphans, find_orphans, run_verify
from ._introspect import write_introspect_manifest
from ._lock import (
    choose_lock_action,
    is_authoritative_run,
    warn_if_lockfile_ignored,
    write_session_lockfile,
)
from ._options import (
    RUN_OPTIONS,
    PruneMode,
    RunOptions,
    add_options,
    is_xdist_worker,
    read_run_options,
    run_options,
    validate_ini_options,
    xdist_is_distributing,
)
from ._session import SESSION_STATE, DittoSession, fail_session, session_state


__all__ = (
    "pytest_addoption",
    "pytest_configure",
    "pytest_sessionstart",
    "pytest_sessionfinish",
    "pytest_unconfigure",
)


def pytest_addoption(parser: pytest.Parser) -> None:
    add_options(parser)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "record(recorder): snapshot with a specific recorder",
    )
    problems = RECORDER_REGISTRY.problems
    if problems:
        raise pytest.UsageError(
            "ditto: the installed recorder plugins break the plugin contract:\n"
            + "\n".join(f"  - {problem.message}" for problem in problems)
        )
    options = read_run_options(config)
    validate_ini_options(config)
    config.stash[RUN_OPTIONS] = options


def pytest_sessionstart(session: pytest.Session) -> None:
    session.config.stash[SESSION_STATE] = DittoSession()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    config = session.config
    options = run_options(config)
    pruned: list[str] = []
    would_prune: list[str] = []

    if not is_xdist_worker(config) and not options.introspect_path:
        if xdist_is_distributing(config):
            # The controller runs no tests under distribution, so its tracker is
            # empty (see #83): anything that needs the whole run's observations
            # would silently check or write nothing. Refuse those modes, and skip
            # the session report, which would be empty.
            _refuse_whole_run_modes_under_xdist(session, options)
            return
        if options.snapshot_mode is SnapshotMode.VERIFY:
            run_verify(session)
            return
        warn_if_lockfile_ignored(config)
        authoritative = is_authoritative_run(session, exitstatus)
        write_session_lockfile(session, choose_lock_action(options, authoritative))
        match options.prune:
            case PruneMode.DELETE:
                pruned = delete_orphans(find_orphans(session))
            case PruneMode.DRY_RUN:
                would_prune = [orphan.key for orphan in find_orphans(session)]
            case PruneMode.OFF:
                pass

    if options.introspect_path:
        write_introspect_manifest(
            options.introspect_path, session_state(config).introspect_backends
        )
        return

    if is_xdist_worker(config):
        # Each worker saw only its share of the tests; a report per worker would
        # be fragmented and interleaved with xdist's own output.
        return

    render_session_report(
        created=session_state(config).tracker.created,
        updated=session_state(config).tracker.updated,
        pruned=pruned,
        would_prune=would_prune,
    )


def _refuse_whole_run_modes_under_xdist(
    session: pytest.Session, options: RunOptions
) -> None:
    """Fail the run for modes that need a single process; warn for a plain run.

    Refusals are printed rather than warned so an `ignore::UserWarning` filter
    cannot hide why the run failed.
    """
    refused = _single_process_mode(options)
    if refused is not None:
        print(
            f"ditto: {refused} needs a single process and cannot run under "
            "pytest-xdist distribution (-n); rerun it with -n 0."
        )
        fail_session(session)
        return
    warn_if_lockfile_ignored(session.config)
    warnings.warn(
        f"{LOCKFILE_NAME} is not maintained under pytest-xdist distribution "
        "(-n); run single-process or `ditto lock` to update it.",
        category=DittoWarning,
        stacklevel=1,
    )


def _single_process_mode(options: RunOptions) -> str | None:
    """Name of the requested mode that needs to observe the whole run, if any."""
    if options.snapshot_mode is SnapshotMode.VERIFY:
        return "--ditto-verify"
    if options.rebuild_lock:
        return "--ditto-lock"
    match options.prune:
        case PruneMode.DELETE:
            return "--ditto-prune"
        case PruneMode.DRY_RUN:
            return "--ditto-prune-dry-run"
        case PruneMode.OFF:
            return None


def pytest_unconfigure(config: pytest.Config) -> None:
    """Close all backend connections after pruning has run in pytest_sessionfinish."""
    state = config.stash.get(SESSION_STATE, None)
    if state is not None:
        state.exit_stack.close()
