from __future__ import annotations

import warnings
from collections.abc import Generator, Sequence
from pathlib import Path

import pytest

from ditto._lockfile import LOCKFILE_NAME
from ditto._results import Activity, ObjectRef, TestPhase
from ditto._report import PrunedSnapshot, render_session_report
from ditto.exceptions import DittoWarning
from ditto.recorders import RECORDER_REGISTRY
from ditto.snapshot import SnapshotMode

from ._drift import (
    delete_orphans,
    find_orphans,
    local_target_ids,
    refuse_shared_prune,
    report_failed_deletions,
    run_verify,
    split_shared,
)
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
from ._result import start_collector, write_session_result
from ._session import SESSION_STATE, DittoSession, collector, session_state


__all__ = (
    "pytest_addoption",
    "pytest_configure",
    "pytest_sessionstart",
    "pytest_ignore_collect",
    "pytest_make_collect_report",
    "pytest_collection_finish",
    "pytest_deselected",
    "pytest_runtest_makereport",
    "pytest_sessionfinish",
    "pytest_sessionfinish_result",
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
    state = session.config.stash[SESSION_STATE] = DittoSession()
    if path := run_options(session.config).result_path:
        state.result = start_collector(session, Path(path))


def _path_nodeid(path: Path, rootpath: Path) -> str | None:
    """Return the node id pytest gives `path`, or None when it's outside `rootpath`."""
    try:
        relative = path.relative_to(rootpath)
    except ValueError:
        return None
    return "" if relative == Path() else relative.as_posix()


@pytest.hookimpl(wrapper=True)
def pytest_ignore_collect(
    collection_path: Path, config: pytest.Config
) -> Generator[None, bool | None, bool | None]:
    ignored = yield
    if (
        ignored
        and (nodeid := _path_nodeid(collection_path, config.rootpath)) is not None
    ):
        session_state(config).collection.uncollected.add(nodeid)
    return ignored


@pytest.hookimpl(wrapper=True)
def pytest_make_collect_report(
    collector: pytest.Collector,
) -> Generator[None, pytest.CollectReport, pytest.CollectReport]:
    report = yield
    if report.skipped:
        session_state(collector.config).collection.uncollected.add(collector.nodeid)
    return report


def pytest_collection_finish(session: pytest.Session) -> None:
    session_state(session.config).collection.collected.update(
        item.nodeid for item in session.items
    )


def pytest_deselected(items: Sequence[pytest.Item]) -> None:
    for item in items:
        session_state(item.config).collection.collected.add(item.nodeid)
        session_state(item.config).collection.deselected.add(item.nodeid)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item,
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    results = collector(item.config)
    if results is not None and report.when in ("setup", "call", "teardown"):
        results.phases.append(
            TestPhase(
                item.nodeid,
                report.when,
                report.outcome,
                hasattr(report, "wasxfail"),
            )
        )
    if report.when == "call" and report.passed:
        session_state(item.config).collection.passed.add(item.nodeid)
    return report


@pytest.hookimpl(wrapper=True, tryfirst=True, specname="pytest_sessionfinish")
def pytest_sessionfinish_result(
    session: pytest.Session,
) -> Generator[None, None, None]:
    # Observe final status after all session-finish hooks, without moving the
    # ordinary maintenance/reporting hook relative to pytest's own hooks.
    results = collector(session.config)
    if results is None or is_xdist_worker(session.config):
        return (yield)
    try:
        yield
    except BaseException as exc:
        results.exit_override = (
            pytest.ExitCode.INTERRUPTED
            if isinstance(exc, KeyboardInterrupt)
            else pytest.ExitCode.INTERNAL_ERROR
        )
        raise
    finally:
        write_session_result(session, results)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    config = session.config
    options = run_options(config)
    pruned: list[PrunedSnapshot] = []
    would_prune: list[PrunedSnapshot] = []

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
                orphans = find_orphans(session)
                if not options.prune_shared:
                    local_ids = local_target_ids(
                        session_state(config).tracker.target_backends,
                        config.rootpath,
                    )
                    orphans, shared = split_shared(orphans, local_ids)
                    if shared:
                        refuse_shared_prune(session, shared)
                results = collector(config)
                result = delete_orphans(
                    orphans, results.activity.append if results else None
                )
                report_failed_deletions(session, result)
                pruned = [
                    PrunedSnapshot(orphan.target_id, orphan.key)
                    for orphan in result.deleted
                ]
            case PruneMode.DRY_RUN:
                would_prune = [
                    PrunedSnapshot(orphan.target_id, orphan.key)
                    for orphan in find_orphans(session)
                ]
            case PruneMode.OFF:
                pass

    if (results := collector(config)) is not None:
        results.activity.extend(
            Activity(
                ObjectRef(o.target_id, o.key),
                "proposed",
                "review",
                "Outside lock in exercised target; legacy prune candidate",
            )
            for o in would_prune
        )

    if options.introspect_path:
        write_introspect_manifest(
            options.introspect_path, session_state(config).introspect_backends
        )
        return

    if is_xdist_worker(config):
        # Each worker saw only its share of the tests; a report per worker would
        # be fragmented and interleaved with xdist's own output.
        return

    if collector(config) is not None:
        # The standalone CLI renders its own report from the handoff.
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
