from __future__ import annotations

import warnings

import pytest

from ditto._lockfile import LOCKFILE_NAME
from ditto._report import render_session_report
from ditto.exceptions import DittoWarning
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
    run_options,
    validate_options,
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
    validate_options(config)
    config.stash[RUN_OPTIONS] = read_run_options(config)


def pytest_sessionstart(session: pytest.Session) -> None:
    session.config.stash[SESSION_STATE] = DittoSession()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    config = session.config
    options = run_options(config)
    pruned: list[str] = []
    would_prune: list[str] = []

    if not is_xdist_worker(config) and not options.introspect_path:
        if options.snapshot_mode is SnapshotMode.VERIFY:
            run_verify(session)
            return
        warn_if_lockfile_ignored(config)
        if xdist_is_distributing(config):
            # The controller saw no snapshots under distribution, so it cannot
            # write the lock correctly (see #83). Refuse an explicit rebuild;
            # only warn for the passive append path.
            if options.rebuild_lock:
                warnings.warn(
                    "--ditto-lock cannot rebuild ditto.lock under pytest-xdist "
                    "distribution; run without -n.",
                    category=DittoWarning,
                    stacklevel=1,
                )
                fail_session(session)
            else:
                warnings.warn(
                    f"{LOCKFILE_NAME} is not maintained under pytest-xdist "
                    "distribution (-n); run single-process or `ditto lock` to "
                    "update it.",
                    category=DittoWarning,
                    stacklevel=1,
                )
            if options.prune is not PruneMode.OFF:
                warnings.warn(
                    "ditto prune is not supported under pytest-xdist distribution "
                    "(-n); run single-process.",
                    category=DittoWarning,
                    stacklevel=1,
                )
        else:
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
