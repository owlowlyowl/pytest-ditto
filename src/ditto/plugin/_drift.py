from __future__ import annotations

import warnings
from collections.abc import MutableMapping

import pytest

from ditto.snapshot import _SessionTracker
from ditto._lockfile import (
    LockEntry,
    LockFile,
    LOCKFILE_NAME,
    _split_nodeid,
    read_lockfile,
    storage_key,
)
from ditto._reconcile import diff_backend, owned_prefixes
from ditto.exceptions import DittoLockFileError, DittoWarning

from ._session import fail_session, session_state


__all__ = ("run_verify", "run_prune")


def _classify_target(
    target_id: str,
    scheme: str,
    backend: MutableMapping[str, bytes],
    lock: LockFile | None,
    session_modules: set[str],
    created_keys: set[str],
) -> tuple[list[str], list[str], list[str]]:
    """Classify one target's drift as (missing, orphan, unsynced) storage keys.

    Shared by verify (reports + fails) and prune (deletes orphans, warns on the
    rest). `orphan` is safe to delete; `unsynced` (created this run, not in lock)
    is not.
    """
    lock_target = lock.targets.get(target_id) if lock is not None else None
    entries = lock_target.entries if lock_target is not None else ()
    lock_keys = {storage_key(e, scheme) for e in entries}
    lock_modules = {_split_nodeid(e.nodeid)[0] for e in entries}
    owned = owned_prefixes(session_modules | lock_modules, scheme)
    result = diff_backend(lock_keys, set(backend), owned, created_keys)
    return list(result.missing), list(result.orphan), list(result.unsynced)


def _session_target_maps(
    tracker: _SessionTracker,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Return (modules_by_target, created_keys_by_target) from this session."""
    modules_by_target: dict[str, set[str]] = {}
    created_by_target: dict[str, set[str]] = {}
    for seen in tracker.lock_accessed:
        modules_by_target.setdefault(seen.target_id, set()).add(
            _split_nodeid(seen.nodeid)[0]
        )
    for seen in tracker.lock_created:
        created_by_target.setdefault(seen.target_id, set()).add(
            storage_key(LockEntry(seen.nodeid, seen.key, seen.recorder), seen.scheme)
        )
    return modules_by_target, created_by_target


def _verify_report_error(message: str) -> None:
    print(f"ditto verify: {message}")


def _verify_report_drift(
    missing: list[str], orphan: list[str], unsynced: list[str]
) -> None:
    print("ditto verify: lock drift detected")
    for k in sorted(missing):
        print(f"  missing (recorded in lock, absent from backend): {k}")
    for k in sorted(orphan):
        print(f"  orphan (in backend, not in lock): {k}")
    for k in sorted(unsynced):
        print(f"  unsynced (produced this run, not in lock — run `ditto lock`): {k}")


def run_verify(session: pytest.Session) -> None:
    """Verify every exercised target against ditto.lock; fail the session on drift."""
    config = session.config
    try:
        lock = read_lockfile(config.rootpath / LOCKFILE_NAME)
    except DittoLockFileError as exc:
        _verify_report_error(str(exc))
        fail_session(session)
        return
    if lock is None:
        _verify_report_error(
            f"no {LOCKFILE_NAME} to verify against; run `ditto lock` to create one."
        )
        fail_session(session)
        return

    tracker = session_state(config).tracker
    modules_by_target, created_by_target = _session_target_maps(tracker)

    opt = session.config.option
    is_partial = bool(getattr(opt, "keyword", "") or getattr(opt, "markexpr", ""))
    if is_partial:
        warnings.warn(
            "ditto verify ran on a partial selection; only exercised targets "
            "were checked (partial verification).",
            category=DittoWarning,
            stacklevel=1,
        )

    all_missing: list[str] = []
    all_orphan: list[str] = []
    all_unsynced: list[str] = []
    for target_id, (scheme, backend) in tracker.target_backends.items():
        try:
            missing, orphan, unsynced = _classify_target(
                target_id,
                scheme,
                backend,
                lock,
                modules_by_target.get(target_id, set()),
                created_by_target.get(target_id, set()),
            )
        except Exception as exc:  # backend unreachable, etc.
            _verify_report_error(f"could not verify {target_id!r}: {exc}")
            fail_session(session)
            continue
        all_missing.extend(missing)
        all_orphan.extend(orphan)
        all_unsynced.extend(unsynced)

    if all_missing or all_orphan or all_unsynced:
        _verify_report_drift(all_missing, all_orphan, all_unsynced)
        fail_session(session)


def _prune_report_error(message: str) -> None:
    print(f"ditto prune: {message}")


def run_prune(session: pytest.Session, *, delete: bool) -> tuple[list[str], list[str]]:
    """Lock-authoritative prune of exercised targets.

    Deletes (or, in dry-run, lists) backend keys absent from the committed lock
    (`orphan`); never touches keys created this run (`unsynced`). Requires a lock —
    refuses (non-zero exit) when absent. Returns `(pruned, would_prune)`.
    """
    config = session.config
    try:
        lock = read_lockfile(config.rootpath / LOCKFILE_NAME)
    except DittoLockFileError as exc:
        _prune_report_error(str(exc))
        fail_session(session)
        return [], []
    if lock is None:
        _prune_report_error(
            f"no {LOCKFILE_NAME} to prune against; run `ditto lock` to create one."
        )
        fail_session(session)
        return [], []

    tracker = session_state(config).tracker
    modules_by_target, created_by_target = _session_target_maps(tracker)

    opt = session.config.option
    if getattr(opt, "keyword", "") or getattr(opt, "markexpr", ""):
        warnings.warn(
            "ditto prune ran on a partial selection; only exercised targets were "
            "considered (partial prune).",
            category=DittoWarning,
            stacklevel=1,
        )

    pruned: list[str] = []
    would_prune: list[str] = []
    for target_id, (scheme, backend) in tracker.target_backends.items():
        try:
            missing, orphan, unsynced = _classify_target(
                target_id,
                scheme,
                backend,
                lock,
                modules_by_target.get(target_id, set()),
                created_by_target.get(target_id, set()),
            )
        except Exception as exc:  # backend unreachable, etc. — skip, never abort
            warnings.warn(
                f"could not prune {target_id!r}: {exc}",
                category=DittoWarning,
                stacklevel=1,
            )
            continue
        for key in unsynced:
            warnings.warn(
                f"ditto prune: {key} was produced this run but is not in the lock "
                "— run `ditto lock`.",
                category=DittoWarning,
                stacklevel=1,
            )
        for key in missing:
            warnings.warn(
                f"ditto prune: {key} is recorded in the lock but absent from the "
                "backend.",
                category=DittoWarning,
                stacklevel=1,
            )
        for key in orphan:
            if not delete:
                would_prune.append(key)
                continue
            try:
                del backend[key]
            except Exception as exc:
                warnings.warn(
                    f"Failed to prune snapshot {key!r}: {exc}",
                    category=DittoWarning,
                    stacklevel=1,
                )
            else:
                pruned.append(key)
    return pruned, would_prune
