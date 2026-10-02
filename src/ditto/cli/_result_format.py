"""Pure text formatting for the minimal standalone operation report."""

from collections import Counter

from ditto._results import ObjectRef, OperationResult


def object_label(object: ObjectRef) -> str:
    """Prefer exact snapshot identity over a backend storage label."""
    identity = object.identity
    if identity is None:
        return object.storage_key
    return f"{identity.nodeid} · {identity.key} · {identity.recorder}"


def operation_lines(result: OperationResult) -> tuple[str, ...]:
    """Describe evidence without performing terminal I/O."""
    counts = Counter(event.outcome for event in result.activity)
    summary = " · ".join(
        f"{counts[word]} {word}"
        for word in ("created", "rewritten", "deleted", "proposed", "failed", "missing")
        if counts[word]
    )
    if not summary:
        summary = (
            "Snapshot activity unavailable"
            if result.completeness == "unsupported"
            else "No snapshot mutations reported"
        )
    lines = [
        f"Ditto report · pytest exit {result.tests.exit_code}",
        f"Scope {result.scope_kind} · {result.scope}",
        summary,
    ]
    for event in result.activity:
        if event.outcome == "accessed":
            continue
        lines.append(
            f"  {event.outcome}  {object_label(event.object)} → {event.object.target}"
        )
        if event.reason:
            lines.append(f"    {event.reason}")
    lines.append(
        f"Lock {result.lock.status} · {len(result.lock.added)} entries added · "
        f"{len(result.lock.removed)} removed"
        if result.lock.status != "unknown"
        else "Lock outcome unknown"
    )
    if result.lock.reason:
        lines.append(result.lock.reason)
    if result.reason:
        lines.append(result.reason)
    for check in result.checks:
        lines.append(f"{check.name}: {check.outcome} · {check.reason}")
        if check.object:
            lines.append(f"  {object_label(check.object)} → {check.object.target}")
        elif check.target:
            lines.append(f"  {check.target}")
    # Only failures: every target a run didn't enumerate is "unchecked", which
    # would bury the report of a plain run. Fuller coverage display is #214's.
    lines.extend(
        f"{coverage.target}: {coverage.status} · {coverage.reason}"
        for coverage in result.coverage
        if coverage.status == "failed"
    )
    return tuple(lines)
