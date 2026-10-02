"""Pure policies for operation evidence and subprocess reconciliation."""

from collections.abc import Sequence, Set as AbstractSet

from msgspec.structs import replace

from ._lockfile import LockFile
from ._results import (
    Coverage,
    Identity,
    LockDelta,
    LockResult,
    OperationResult,
    safe_location,
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
        LockDelta(safe_location(target), Identity(nodeid, key, recorder))
        for target, nodeid, key, recorder in sorted(items)
    )


def lock_result(
    before: LockFile | None,
    after: LockFile | None,
    initial_error: str | None,
    final_error: str | None,
    failure: str | None,
) -> LockResult:
    """Describe observed lock changes independently of snapshot mutations."""
    if final_error:
        return LockResult(reason=f"{final_error} reading final lock")
    if initial_error:
        return LockResult(reason="Initial lock unreadable; deltas unknown")
    before_entries, after_entries = _entries(before), _entries(after)
    status = "unchanged" if after == before else "written"
    if failure:
        status = "failed"
    return LockResult(
        status,
        _delta(after_entries - before_entries),
        _delta(before_entries - after_entries),
        failure,
    )


def target_coverage(
    observed: Sequence[Coverage],
    runtime_targets: AbstractSet[str],
    historical_targets: AbstractSet[str],
) -> tuple[Coverage, ...]:
    """Retain uninspected runtime and historical targets as explicit unknowns."""
    coverage = tuple(observed)
    seen = {item.target for item in coverage}
    runtime = tuple(
        Coverage(
            safe_location(target),
            "runtime",
            "unchecked",
            "Runtime target resolved; physical inventory not enumerated",
        )
        for target in sorted(runtime_targets)
        if safe_location(target) not in seen
    )
    seen.update(item.target for item in runtime)
    historical = tuple(
        Coverage(
            safe_location(target),
            "lock",
            "unchecked",
            "Historical target not resolved or inspected",
        )
        for target in sorted(historical_targets)
        if safe_location(target) not in seen
    )
    return coverage + runtime + historical


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


def finalize_result(result: OperationResult) -> OperationResult:
    """Failed or unexamined collection cannot establish complete discovery."""
    if result.tests.exit_code == 0 and not result.tests.uncollected:
        return replace(result, completeness="complete")
    return replace(
        result,
        completeness="incomplete",
        scope_kind="unknown" if result.tests.exit_code else result.scope_kind,
        reason="Run failed, interrupted, or has unexamined collection",
    )


def unsupported_result(result: OperationResult) -> OperationResult:
    """Distributed collection cannot establish aggregate snapshot outcomes."""
    return replace(
        result,
        completeness="unsupported",
        scope_kind="unknown",
        reason="Snapshot aggregation under pytest-xdist is unsupported",
    )
