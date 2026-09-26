from __future__ import annotations

import warnings

import pytest

from ditto._lockfile import LOCKFILE_NAME
from ditto._report import render_session_report
from ditto.exceptions import DittoWarning

from ._drift import run_prune, run_verify
from ._introspect import write_introspect_manifest
from ._lock import warn_if_lockfile_ignored, write_session_lockfile
from ._options import (
    add_options,
    is_xdist_worker,
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


def pytest_sessionstart(session: pytest.Session) -> None:
    session.config.stash[SESSION_STATE] = DittoSession()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    config = session.config
    pruned: list[str] = []
    would_prune: list[str] = []

    if not is_xdist_worker(config) and not config.getoption(
        "--ditto-introspect", default=""
    ):
        if config.getoption("--ditto-verify", default=False):
            run_verify(session)
            return
        warn_if_lockfile_ignored(config)
        is_lock: bool = bool(config.getoption("--ditto-lock", default=False))
        do_prune: bool = bool(config.getoption("--ditto-prune", default=False))
        dry_run: bool = bool(config.getoption("--ditto-prune-dry-run", default=False))
        if xdist_is_distributing(config):
            # The controller saw no snapshots under distribution, so it cannot
            # write the lock correctly (see #83). Refuse an explicit rebuild;
            # only warn for the passive append path.
            if is_lock:
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
            if do_prune or dry_run:
                warnings.warn(
                    "ditto prune is not supported under pytest-xdist distribution "
                    "(-n); run single-process.",
                    category=DittoWarning,
                    stacklevel=1,
                )
        else:
            pruning = do_prune or dry_run
            write_session_lockfile(
                session, exitstatus, is_lock=is_lock, pruning=pruning
            )
            if pruning:
                pruned, would_prune = run_prune(session, delete=do_prune)

    introspect_path = config.getoption("--ditto-introspect", default="")
    if introspect_path:
        write_introspect_manifest(
            introspect_path, session_state(config).introspect_backends
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
