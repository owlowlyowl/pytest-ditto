from __future__ import annotations

import warnings
from collections.abc import Iterable, Mapping, MutableMapping, Sequence, Set
from dataclasses import dataclass
from pathlib import Path

import pytest

from ditto.snapshot import _RegisteredTarget, _SessionTracker
from ditto._lockfile import (
    LockEntry,
    LockFile,
    LOCKFILE_NAME,
    split_nodeid,
    read_lockfile,
    storage_key,
)
from ditto._reconcile import diff_backend, owned_prefixes
from ditto.exceptions import DittoLockFileError, DittoWarning

from ._session import fail_session, session_state
from ._targets import is_checkout_local


__all__ = (
    "Orphan",
    "TargetDrift",
    "FailedDeletion",
    "PruneResult",
    "run_verify",
    "find_orphans",
    "local_target_ids",
    "split_shared",
    "refuse_shared_prune",
    "delete_orphans",
    "report_failed_deletions",
)


@dataclass(frozen=True)
class Orphan:
    """A backend key under the suite's modules that `ditto.lock` doesn't record."""

    target_id: str
    backend: MutableMapping[str, bytes]
    key: str


@dataclass(frozen=True)
class TargetDrift:
    """One target's lock drift, kept per target so the report can name it.

    Two targets can hold the same storage key, so a flat list of keys is
    ambiguous: only the target says which backend needs attention. `scheme`
    identifies how the target stores its keys.
    """

    target_id: str
    scheme: str
    missing: list[str]
    orphan: list[str]
    unsynced: list[str]


@dataclass(frozen=True)
class FailedDeletion:
    """An orphan whose deletion raised, and the error it raised."""

    orphan: Orphan
    reason: str


@dataclass(frozen=True)
class PruneResult:
    """The orphans a prune deleted and those it failed to delete."""

    deleted: list[Orphan]
    failed: list[FailedDeletion]


def _classify_target(
    target_id: str,
    scheme: str,
    backend: MutableMapping[str, bytes],
    lock: LockFile | None,
    session_modules: set[str],
    created_keys: set[str],
) -> TargetDrift:
    """Classify one target's drift as its missing, orphan and unsynced storage keys.

    Shared by verify (reports + fails) and prune (deletes orphans, warns on the
    rest). `orphan` is safe to delete; `unsynced` (created this run, not in lock)
    is not.
    """
    lock_target = lock.targets.get(target_id) if lock is not None else None
    entries = lock_target.entries if lock_target is not None else ()
    lock_keys = {storage_key(e, scheme) for e in entries}
    lock_modules = {split_nodeid(e.nodeid)[0] for e in entries}
    owned = owned_prefixes(session_modules | lock_modules, scheme)
    result = diff_backend(lock_keys, set(backend), owned, created_keys)
    return TargetDrift(
        target_id,
        scheme,
        list(result.missing),
        list(result.orphan),
        list(result.unsynced),
    )


def _session_target_maps(
    tracker: _SessionTracker,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Return (modules_by_target, created_keys_by_target) from this session."""
    modules_by_target: dict[str, set[str]] = {}
    created_by_target: dict[str, set[str]] = {}
    for seen in tracker.lock_accessed:
        modules_by_target.setdefault(seen.target_id, set()).add(
            split_nodeid(seen.nodeid)[0]
        )
    for seen in tracker.lock_created:
        created_by_target.setdefault(seen.target_id, set()).add(
            storage_key(LockEntry(seen.nodeid, seen.key, seen.recorder), seen.scheme)
        )
    return modules_by_target, created_by_target


def _verify_say(session: pytest.Session, lines: list[str]) -> None:
    """Print verify's report on lines of its own, after pytest's progress output."""
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        print("\n".join(lines))
        return
    # pytest leaves its progress line (`..  [100%]`) open until after this hook;
    # `ensure_newline` only closes it in verbose mode. Not printed from
    # `pytest_terminal_summary`, which `--no-summary` would silence.
    if reporter._tw.width_of_current_line:
        reporter._tw.line()
    for line in lines:
        reporter.write_line(line)


def _verify_report_error(session: pytest.Session, message: str) -> None:
    _verify_say(session, [f"ditto verify: {message}"])


# Each drift kind: its heading, and how to fix the keys listed under it.
_DRIFT_LABELS = (
    (
        "missing",
        "missing (recorded in lock, absent from backend)",
        "`ditto run` records them again; `ditto lock` drops them if their "
        "tests are gone",
    ),
    (
        "orphan",
        "orphan (in backend, not in lock)",
        "`ditto prune` deletes them (`ditto prune --check` to preview)",
    ),
    (
        "unsynced",
        "unsynced (produced this run, not in lock)",
        "`ditto lock` records them",
    ),
)


def _target_identities(
    lock: LockFile, target_id: str, scheme: str
) -> dict[str, LockEntry]:
    """The storage keys `lock` records in one target, mapped to their entry.

    A stored name shortens and replaces characters of the test name and key, so
    the lock is where their exact values are.
    """
    target = lock.targets.get(target_id)
    if target is None:
        return {}
    return {storage_key(entry, scheme): entry for entry in target.entries}


def _drift_key_label(key: str, identities: Mapping[str, LockEntry]) -> str:
    """Name a drifted key by the test the lock records, else by its storage name.

    The lock holds no entry for an orphan or an unsynced key — that is what
    makes them drift — so those are named by storage name alone.
    """
    entry = identities.get(key)
    if entry is None:
        return key
    return f"{entry.nodeid}  {entry.key}  {key}"


def _drift_lines(drift: TargetDrift, identities: Mapping[str, LockEntry]) -> list[str]:
    """The report lines for one target's drift, indented under the target's id."""
    lines = [f"  {drift.target_id}:"]
    for field, label, fix in _DRIFT_LABELS:
        keys = sorted(getattr(drift, field))
        if keys:
            lines.append(f"    {label}:")
            lines.extend(f"      {_drift_key_label(k, identities)}" for k in keys)
            lines.append(f"      fix: {fix}")
    return lines


def _verify_report_drift(
    session: pytest.Session, drift: list[TargetDrift], lock: LockFile
) -> None:
    """Print each target's drift, grouped by the target that holds it."""
    lines = ["ditto verify: lock drift detected"]
    for target_drift in drift:
        identities = _target_identities(
            lock, target_drift.target_id, target_drift.scheme
        )
        lines.extend(_drift_lines(target_drift, identities))
    _verify_say(session, lines)


def _no_drift_line(target_ids: list[str]) -> str:
    """What a verify without drift checked: its targets, or that there were none."""
    if not target_ids:
        return (
            "ditto verify: no snapshot target was used, so nothing was checked "
            "against ditto.lock."
        )
    plural = "s" if len(target_ids) != 1 else ""
    return f"ditto verify: no drift in {len(target_ids)} target{plural}: " + ", ".join(
        sorted(target_ids)
    )


def run_verify(session: pytest.Session) -> None:
    """Verify every exercised target against ditto.lock; fail the session on drift."""
    config = session.config
    try:
        lock = read_lockfile(config.rootpath / LOCKFILE_NAME)
    except DittoLockFileError as exc:
        _verify_report_error(session, str(exc))
        fail_session(session)
        return
    if lock is None:
        _verify_report_error(
            session,
            f"no {LOCKFILE_NAME} to verify against; run `ditto lock` to create one.",
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

    drift: list[TargetDrift] = []
    unreadable = False
    for target_id, target in tracker.target_backends.items():
        try:
            target_drift = _classify_target(
                target_id,
                target.scheme,
                target.backend,
                lock,
                modules_by_target.get(target_id, set()),
                created_by_target.get(target_id, set()),
            )
        except Exception as exc:  # backend unreachable, etc.
            _verify_report_error(
                session,
                f"could not read {target_id!r}, so its snapshots weren't checked: "
                f"{exc}",
            )
            fail_session(session)
            unreadable = True
            continue
        drift.append(target_drift)

    drifted = [d for d in drift if d.missing or d.orphan or d.unsynced]
    if drifted:
        _verify_report_drift(session, drifted, lock)
        fail_session(session)
    elif not unreadable:
        _verify_say(session, [_no_drift_line([d.target_id for d in drift])])


def _prune_report_error(message: str) -> None:
    print(f"ditto prune: {message}")


def find_orphans(session: pytest.Session) -> list[Orphan]:
    """Return the backend keys absent from `ditto.lock` in the exercised targets.

    Keys created this run (`unsynced`) are never orphans; they, and keys the lock
    records but the backend lacks (`missing`), are warned about instead. Requires
    a lock: when it is absent or unreadable, reports why, fails the session, and
    returns no orphans. A target that cannot be read is reported and fails the
    session, and the other targets are still checked.
    """
    config = session.config
    try:
        lock = read_lockfile(config.rootpath / LOCKFILE_NAME)
    except DittoLockFileError as exc:
        _prune_report_error(str(exc))
        fail_session(session)
        return []
    if lock is None:
        _prune_report_error(
            f"no {LOCKFILE_NAME} to prune against; run `ditto lock` to create one."
        )
        fail_session(session)
        return []

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

    orphans: list[Orphan] = []
    for target_id, target in tracker.target_backends.items():
        try:
            drift = _classify_target(
                target_id,
                target.scheme,
                target.backend,
                lock,
                modules_by_target.get(target_id, set()),
                created_by_target.get(target_id, set()),
            )
        except Exception as exc:  # backend unreachable, etc.
            _prune_report_error(f"could not read {target_id!r}: {exc}")
            fail_session(session)
            continue
        for key in sorted(drift.unsynced):
            warnings.warn(
                f"ditto prune: {target_id!r}: {key} was produced this run but is "
                "not in the lock; run `ditto lock`.",
                category=DittoWarning,
                stacklevel=1,
            )
        for key in sorted(drift.missing):
            warnings.warn(
                f"ditto prune: {target_id!r}: {key} is recorded in the lock but "
                "absent from the backend.",
                category=DittoWarning,
                stacklevel=1,
            )
        orphans.extend(Orphan(target_id, target.backend, key) for key in drift.orphan)
    return orphans


def local_target_ids(
    targets: Mapping[str, _RegisteredTarget], rootdir: Path
) -> set[str]:
    """Return the ids of `targets` whose paths resolve inside `rootdir` now.

    Decided when prune runs, not when a target was first used, because a
    `file://` backend follows its path again on every operation. A path that
    can't be resolved (a symlink loop, say) is warned about and left out, so
    it counts as shared.
    """
    local: set[str] = set()
    for target_id, target in targets.items():
        try:
            if is_checkout_local(target.canonical_uri, rootdir):
                local.add(target_id)
        except (OSError, RuntimeError) as exc:
            warnings.warn(
                f"ditto prune: could not resolve {target_id!r} ({exc}); treating "
                "it as shared.",
                category=DittoWarning,
                stacklevel=1,
            )
    return local


def split_shared(
    orphans: Sequence[Orphan], local_ids: Set[str]
) -> tuple[list[Orphan], list[Orphan]]:
    """Split `orphans` into those in checkout-local targets and those in shared ones.

    Prune decides what this suite owns from its test-module paths, which other
    branches of the project, or other projects with the same paths, share. On
    a target they also write to, their snapshots look like this checkout's
    orphans. A target whose id isn't in `local_ids` counts as shared.
    """
    local = [o for o in orphans if o.target_id in local_ids]
    shared = [o for o in orphans if o.target_id not in local_ids]
    return local, shared


def refuse_shared_prune(session: pytest.Session, shared: Sequence[Orphan]) -> None:
    """Report each shared target prune won't delete from, and fail the run."""
    counts: dict[str, int] = {}
    for orphan in shared:
        counts[orphan.target_id] = counts.get(orphan.target_id, 0) + 1
    for target_id, count in sorted(counts.items()):
        _prune_report_error(
            f"not deleting {count} snapshot(s) from {target_id!r}: other "
            "branches or projects may write to it, and their snapshots look like "
            "orphans to this checkout. Give each its own target path, then pass "
            "--ditto-prune-shared (`ditto prune --shared`); "
            "`ditto prune --check` lists what would be deleted."
        )
    fail_session(session)


def delete_orphans(orphans: Iterable[Orphan]) -> PruneResult:
    """Delete each orphan from its backend, carrying on past a failed deletion."""
    deleted: list[Orphan] = []
    failed: list[FailedDeletion] = []
    for orphan in orphans:
        try:
            del orphan.backend[orphan.key]
        except Exception as exc:
            failed.append(FailedDeletion(orphan, str(exc)))
        else:
            deleted.append(orphan)
    return PruneResult(deleted, failed)


def report_failed_deletions(session: pytest.Session, result: PruneResult) -> None:
    """Report each target's failed deletions, if any, and fail the run."""
    if not result.failed:
        return
    deleted_counts: dict[str, int] = {}
    for orphan in result.deleted:
        deleted_counts[orphan.target_id] = deleted_counts.get(orphan.target_id, 0) + 1
    failed_by_target: dict[str, list[FailedDeletion]] = {}
    for failure in result.failed:
        failed_by_target.setdefault(failure.orphan.target_id, []).append(failure)
    for target_id, failures in sorted(failed_by_target.items()):
        deleted = deleted_counts.get(target_id, 0)
        _prune_report_error(
            f"deleted {deleted} of {deleted + len(failures)} snapshot(s) from "
            f"{target_id!r}; {len(failures)} could not be deleted:"
        )
        for failure in sorted(failures, key=lambda f: f.orphan.key):
            print(f"  {failure.orphan.key}: {failure.reason}")
    fail_session(session)
