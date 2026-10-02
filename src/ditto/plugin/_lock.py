from __future__ import annotations

import re
import warnings
from collections.abc import Iterable, Iterator
from enum import Enum

import pytest

from ditto.snapshot import LockSeen, SnapshotMode
from ditto._lockfile import (
    LockEntry,
    LockFile,
    LockTarget,
    LOCKFILE_NAME,
    LOCKFILE_VERSION,
    merge_append,
    read_lockfile,
    write_lockfile,
)
from ditto.exceptions import DittoLockFileError, DittoWarning

from ._options import PruneMode, RunOptions
from ._session import CollectionRecord, fail_session, session_state


__all__ = (
    "LockAction",
    "choose_lock_action",
    "is_authoritative_run",
    "keeps_entry",
    "write_session_lockfile",
    "warn_if_lockfile_ignored",
)


class LockAction(Enum):
    """What a single-process session does to `ditto.lock` when it finishes.

    Attributes
    ----------
    APPEND
        Add the entries created this run.
    REBUILD
        Rewrite each exercised target's entries from this run.
    REFUSE
        `--ditto-lock` on a run that cannot rebuild the lock: warn and fail.
    KEEP
        Leave the lock unchanged. A prune run keeps it so a snapshot created
        this run stays `unsynced` (kept and warned) rather than being appended.
    """

    APPEND = "append"
    REBUILD = "rebuild"
    REFUSE = "refuse"
    KEEP = "keep"


def _grouped(seen: set[LockSeen]) -> dict[tuple[str, str], list[LockEntry]]:
    """Group lock observations by `(target_id, scheme)`."""
    grouped: dict[tuple[str, str], list[LockEntry]] = {}
    for obs in seen:
        grouped.setdefault((obs.target_id, obs.scheme), []).append(
            LockEntry(obs.nodeid, obs.key, obs.recorder)
        )
    return grouped


def _append_lockfile(config: pytest.Config) -> None:
    """Union this session's newly-created entries into `ditto.lock` (append-only)."""
    grouped = _grouped(session_state(config).tracker.lock_created)
    if not grouped:
        return
    path = config.rootpath / LOCKFILE_NAME
    existing = read_lockfile(path)
    lock = existing
    for (target_id, scheme), entries in grouped.items():
        lock = merge_append(lock, target_id, scheme, entries)
    # `grouped` is non-empty (guarded above), so the loop runs and `lock` is a
    # LockFile; the `is not None` keeps that explicit for the type checker.
    if lock is not None and lock != existing:
        write_lockfile(path, lock)


def is_authoritative_run(session: pytest.Session, exitstatus: int) -> bool:
    """True when this run is safe to rebuild the lock file from.

    Refuses filtered runs (`-k`, `-m`, `--lf`/`--ff`), positional path/nodeid
    narrowing (`pytest tests/foo.py` or `::nodeid`), runs with failures, and runs
    that did not exit cleanly. The `exitstatus` check catches collection errors
    (a module that fails to import leaves `testsfailed == 0` yet a non-zero exit),
    which would otherwise let a partial collection rebuild and silently shrink the
    lock.

    Notes
    -----
    Positional narrowing is refused outright (#82): a path/nodeid run can silently
    truncate entries for files it did not collect from a shared target. An
    alternative considered was *module-scoped preservation* — rewriting only the
    entries for modules actually exercised this run and preserving the rest, which
    would make file/dir narrowing safe without refusing. It was rejected because it
    still cannot make nodeid narrowing safe (that sub-selects within a module) and
    it stops a full run from ever cleaning entries for deleted files. Refusing is
    simpler and safe; `ditto lock` with no positional args is the supported full
    rebuild.
    """
    opt = session.config.option
    # Any truthy signal here means the run was narrowed or filtered and is not
    # authoritative over the full keyspace. Add new narrowing options to the tuple.
    narrowing = (
        getattr(opt, "keyword", ""),  # -k
        getattr(opt, "markexpr", ""),  # -m
        getattr(opt, "last_failed", False),  # --lf
        getattr(opt, "failed_first", False),  # --ff
        getattr(opt, "file_or_dir", None),  # positional path/nodeid args
    )
    if any(narrowing):
        return False
    return session.testsfailed == 0 and exitstatus == 0


def _containing_nodeids(nodeid: str) -> Iterator[str]:
    """Yield `nodeid` and the node ids that contain it.

    For `tests/test_x.py::TestC::test_m` that is `""` (the root directory),
    `tests`, `tests/test_x.py`, `tests/test_x.py::TestC` and the node id itself.
    """
    yield ""
    for boundary in re.finditer(r"/|::", nodeid):
        yield nodeid[: boundary.start()]
    yield nodeid


def keeps_entry(nodeid: str, collection: CollectionRecord) -> bool:
    """Whether a rebuild keeps an existing entry this run didn't replace.

    A test that passed has its entries replaced by what it used this run. A
    test that was collected but didn't pass (skipped, xfailed, deselected), or
    that pytest didn't collect because it ignored a path above the test or a
    collector above it skipped, keeps its entries, so a skip on one machine
    never drops a baseline another machine still runs. An entry for a test that
    no longer exists is dropped.
    """
    if nodeid in collection.passed:
        return False
    return nodeid in collection.collected or any(
        node in collection.uncollected for node in _containing_nodeids(nodeid)
    )


def _rebuilt_target(
    current: LockTarget | None,
    scheme: str,
    entries: Iterable[LockEntry],
    collection: CollectionRecord,
) -> LockTarget:
    """Return a target's rebuilt entries: this run's plus the existing ones kept.

    A target's scheme is intrinsic to its id, so an existing target keeps its
    scheme (matching `merge_append`); `scheme` is used only for a new target.
    """
    if current is None:
        return LockTarget(scheme=scheme, entries=tuple(sorted(set(entries))))
    kept = {e for e in current.entries if keeps_entry(e.nodeid, collection)}
    return LockTarget(scheme=current.scheme, entries=tuple(sorted(set(entries) | kept)))


def _rewrite_lockfile(config: pytest.Config) -> None:
    """Rebuild each exercised target's entries from this run, test by test.

    Targets present in the existing file but not exercised this run are
    preserved; see `_rebuilt_target` for an exercised one.
    """
    state = session_state(config)
    grouped = _grouped(state.tracker.lock_accessed)
    path = config.rootpath / LOCKFILE_NAME
    # An authoritative rebuild must be able to recover a corrupt lock file, so a
    # parse failure of the existing file is downgraded to "start fresh" rather
    # than aborting (see #85). Entries for unexercised targets in a corrupt file
    # are unrecoverable, which is acceptable for a from-scratch rebuild.
    try:
        existing = read_lockfile(path)
    except DittoLockFileError as exc:
        warnings.warn(
            f"Replacing unreadable {LOCKFILE_NAME} ({exc}).",
            category=DittoWarning,
            stacklevel=1,
        )
        existing = None
    targets = dict(existing.targets) if existing is not None else {}
    for (target_id, scheme), entries in grouped.items():
        targets[target_id] = _rebuilt_target(
            targets.get(target_id), scheme, entries, state.collection
        )
    lock = LockFile(version=LOCKFILE_VERSION, targets=targets)
    if lock != existing:
        write_lockfile(path, lock)


def warn_if_lockfile_ignored(config: pytest.Config) -> None:
    """Warn if ditto.lock matches a .gitignore pattern — it must be committed."""
    gitignore = config.rootpath / ".gitignore"
    if not gitignore.exists():
        return
    patterns = {
        line.strip()
        for line in gitignore.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    # Exact-match only — a literal `ditto.lock` / `/ditto.lock` line. Broader
    # globs (e.g. `*.lock`) are not detected; full gitignore semantics are out
    # of scope for a best-effort warning.
    if LOCKFILE_NAME in patterns or f"/{LOCKFILE_NAME}" in patterns:
        warnings.warn(
            f"{LOCKFILE_NAME} matches a .gitignore pattern but must be committed "
            "to do its job; remove the ignore rule.",
            category=DittoWarning,
            stacklevel=1,
        )


def choose_lock_action(options: RunOptions, authoritative: bool) -> LockAction:
    """Decide what the session does to `ditto.lock`.

    Parameters
    ----------
    options : RunOptions
        The run's ditto options.
    authoritative : bool
        Whether the run is safe to rebuild the lock from; see
        `is_authoritative_run`.
    """
    if options.rebuild_lock:
        return LockAction.REBUILD if authoritative else LockAction.REFUSE
    if options.snapshot_mode is SnapshotMode.UPDATE and authoritative:
        return LockAction.REBUILD
    if options.prune is not PruneMode.OFF:
        return LockAction.KEEP
    return LockAction.APPEND


def _fail_run(session: pytest.Session, message: str) -> None:
    """Print why the run fails, then fail it.

    Printed rather than warned, so a warning filter can't hide why it failed.
    """
    print(f"ditto: {message}")
    fail_session(session)


def write_session_lockfile(session: pytest.Session, action: LockAction) -> None:
    """Apply `action` to `ditto.lock` for a single-process run.

    Never raises. A refused rebuild fails the run, and so does a rebuild
    (`--ditto-lock`, or `--ditto-update` on a full run) that can't write the
    lock: it's lock maintenance the user asked for. An ordinary run's append
    that can't write the lock only warns: a test run shouldn't fail over lock
    bookkeeping.
    """
    match action:
        case LockAction.KEEP:
            return
        case LockAction.REFUSE:
            session_state(
                session.config
            ).lock_failure = "Lock rebuild refused: incomplete run"
            _fail_run(
                session,
                "--ditto-lock requires a full run (no -k/-m/--lf, no path/nodeid "
                f"args, and no failures); leaving {LOCKFILE_NAME} unchanged.",
            )
            return
        case LockAction.APPEND:
            write = _append_lockfile
        case LockAction.REBUILD:
            write = _rewrite_lockfile
    try:
        write(session.config)
    except Exception as exc:  # never crash a run over a lock-file write
        session_state(
            session.config
        ).lock_failure = f"{type(exc).__name__} during lock maintenance"
        if action is LockAction.REBUILD:
            _fail_run(session, f"failed to write {LOCKFILE_NAME}: {exc}")
        else:
            warnings.warn(
                f"Failed to write {LOCKFILE_NAME}: {exc}",
                category=DittoWarning,
                stacklevel=1,
            )
