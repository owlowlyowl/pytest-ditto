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
    add_options,
    is_xdist_worker,
    read_run_options,
    reject_single_process_modes_under_xdist,
    run_options,
    validate_ini_options,
    xdist_is_distributing,
)
from ._session import SESSION_STATE, DittoSession, session_state


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
    reject_single_process_modes_under_xdist(config, options)
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
            # empty (see #83). Verify, lock and prune were refused at configure
            # time; a plain run can't maintain the lock, and its report would be
            # empty.
            warn_if_lockfile_ignored(config)
            warnings.warn(
                f"{LOCKFILE_NAME} is not maintained under pytest-xdist "
                "distribution (-n); run single-process or `ditto lock` to "
                "update it.",
                category=DittoWarning,
                stacklevel=1,
            )
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


def pytest_unconfigure(config: pytest.Config) -> None:
    """Close all backend connections after pruning has run in pytest_sessionfinish."""
    state = config.stash.get(SESSION_STATE, None)
    if state is not None:
        state.exit_stack.close()
