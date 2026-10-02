"""Pure policies for operation evidence and subprocess reconciliation.

Targets stay unmasked while results are compared and combined, so targets that
differ only by a secret stay distinct; `redact_targets` masks them on the way out.
"""

from collections.abc import Mapping, Set as AbstractSet
from dataclasses import dataclass
from typing import Literal

from msgspec.structs import replace

from ._credentials import mask_credentials
from ._lockfile import LockFile
from ._results import (
    Check,
    Completeness,
    Coverage,
    Identity,
    LockDelta,
    LockResult,
    ObjectRef,
    OperationResult,
    ScopeKind,
)


def _entries(lock: LockFile | None) -> set[tuple[str, str, str, str]]:
    return (
        {
            (target, entry.nodeid, entry.key, entry.recorder)
            for target, group in lock.targets.items()
            for entry in group.entries
        }
        if lock
        else set()
    )


def _delta(items: AbstractSet[tuple[str, str, str, str]]) -> tuple[LockDelta, ...]:
    return tuple(
        LockDelta(target, Identity(nodeid, key, recorder))
        for target, nodeid, key, recorder in sorted(items)
    )


@dataclass(frozen=True)
class LockProblem:
    """Why lock maintenance didn't do what was asked: it failed, or was refused."""

    status: Literal["failed", "refused"]
    reason: str


def lock_result(
    before: LockFile | None,
    after: LockFile | None,
    initial_error: str | None,
    final_error: str | None,
    problem: LockProblem | None,
) -> LockResult:
    """Describe observed lock changes independently of snapshot mutations."""
    if final_error:
        return LockResult(reason=f"{final_error} reading final lock")
    if initial_error:
        return LockResult(reason="Initial lock unreadable; deltas unknown")
    before_entries, after_entries = _entries(before), _entries(after)
    added = _delta(after_entries - before_entries)
    removed = _delta(before_entries - after_entries)
    if problem is not None:
        return LockResult(problem.status, added, removed, problem.reason)
    return LockResult("unchanged" if after == before else "written", added, removed)


def target_coverage(
    observed: Mapping[str, Coverage],
    runtime_targets: AbstractSet[str],
    historical_targets: AbstractSet[str],
) -> tuple[Coverage, ...]:
    """Retain uninspected runtime and historical targets as explicit unknowns.

    `observed` is keyed by unmasked target id, as are both target sets.
    """
    runtime = {
        target: Coverage(
            target,
            "runtime",
            "unchecked",
            "Runtime target resolved; physical inventory not enumerated",
        )
        for target in sorted(runtime_targets - observed.keys())
    }
    historical = tuple(
        Coverage(
            target,
            "lock",
            "unchecked",
            "Historical target not resolved or inspected",
        )
        for target in sorted(historical_targets - observed.keys() - runtime.keys())
    )
    return tuple(observed.values()) + tuple(runtime.values()) + historical


def _redact_ref(ref: ObjectRef) -> ObjectRef:
    return replace(ref, target=mask_credentials(ref.target))


def _redact_check(check: Check) -> Check:
    return replace(
        check,
        object=_redact_ref(check.object) if check.object else None,
        target=mask_credentials(check.target) if check.target else None,
    )


def _redact_deltas(deltas: tuple[LockDelta, ...]) -> tuple[LockDelta, ...]:
    return tuple(replace(d, target=mask_credentials(d.target)) for d in deltas)


def redact_targets(result: OperationResult) -> OperationResult:
    """Mask credentials in every target, after all comparisons used unmasked ids."""
    return replace(
        result,
        activity=tuple(
            replace(event, object=_redact_ref(event.object))
            for event in result.activity
        ),
        coverage=tuple(
            replace(item, target=mask_credentials(item.target))
            for item in result.coverage
        ),
        checks=tuple(_redact_check(check) for check in result.checks),
        lock=replace(
            result.lock,
            added=_redact_deltas(result.lock.added),
            removed=_redact_deltas(result.lock.removed),
        ),
    )


def reconcile_exit(result: OperationResult, status: int) -> OperationResult:
    """Preserve completed events while trusting the actual subprocess status."""
    if result.tests.exit_code == status:
        return result
    return replace(
        result,
        tests=replace(result.tests, exit_code=status),
        completeness="incomplete",
        scope_kind="unknown",
        reason="Subprocess status differs from handoff; coverage incomplete",
    )


def classify(
    status: int, *, full: bool, uncollected: bool, distributing: bool
) -> tuple[Completeness, ScopeKind, str | None]:
    """How much of the suite a run's evidence covers, and why it's short.

    A failed or interrupted run can't establish complete discovery, and its
    scope is unknown; neither can a run that left collection unexamined.
    """
    if distributing:
        return (
            "unsupported",
            "unknown",
            "Snapshot aggregation under pytest-xdist is unsupported",
        )
    if status != 0 or uncollected:
        return (
            "incomplete",
            "unknown" if status else "selected",
            "Run failed, interrupted, or has unexamined collection",
        )
    return "complete", "full" if full else "selected", None
