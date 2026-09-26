from __future__ import annotations

import warnings

import pytest

from ditto.snapshot import LockSeen
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

from ._session import fail_session, session_state


__all__ = ("write_session_lockfile", "warn_if_lockfile_ignored")


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


def _is_authoritative_run(session: pytest.Session, exitstatus: int) -> bool:
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


def _rewrite_lockfile(config: pytest.Config) -> None:
    """Rewrite each exercised target's entries to this run's accessed-or-created set.

    Targets present in the existing file but not exercised this run are preserved.
    """
    grouped = _grouped(session_state(config).tracker.lock_accessed)
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
        # A target's scheme is intrinsic to its id; preserve the existing one
        # (matching merge_append) and only use the observed scheme for a new target.
        current = targets.get(target_id)
        target_scheme = current.scheme if current is not None else scheme
        targets[target_id] = LockTarget(
            scheme=target_scheme, entries=tuple(sorted(set(entries)))
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


def write_session_lockfile(
    session: pytest.Session,
    exitstatus: int,
    *,
    is_lock: bool,
    pruning: bool,
) -> None:
    """Rewrite, append, or leave ditto.lock unchanged for a single-process run.

    A prune run (`pruning`) leaves the lock untouched so a snapshot created this
    run stays `unsynced` (kept and warned) rather than being silently appended.
    Never raises — a lock-write failure is downgraded to a `DittoWarning`.
    """
    config = session.config
    try:
        if is_lock:
            if _is_authoritative_run(session, exitstatus):
                _rewrite_lockfile(config)
            else:
                warnings.warn(
                    "--ditto-lock requires a full run (no -k/-m/--lf, no "
                    "path/nodeid args, and no failures); leaving "
                    "ditto.lock unchanged.",
                    category=DittoWarning,
                    stacklevel=1,
                )
                fail_session(session)
        elif config.getoption(
            "--ditto-update", default=False
        ) and _is_authoritative_run(session, exitstatus):
            _rewrite_lockfile(config)
        elif pruning:
            # A prune run does not write the lock (see docstring).
            pass
        else:
            _append_lockfile(config)
    except Exception as exc:  # never crash a run over a lock-file write
        warnings.warn(
            f"Failed to write {LOCKFILE_NAME}: {exc}",
            category=DittoWarning,
            stacklevel=1,
        )
