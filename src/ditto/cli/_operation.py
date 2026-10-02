"""Subprocess handoff lifecycle and a minimal standalone result consumer.

The shared Rich policy and fuller operation rendering are separate follow-ups.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from msgspec.structs import replace
from rich.console import Console
from rich.text import Text

from ditto._results import OperationResult, decode_result


def render_operation(result: OperationResult, console: Console) -> None:
    console.print(Text(f"Ditto report · pytest exit {result.tests.exit_code}"))
    console.print(Text(f"Scope {result.scope_kind} · {result.scope}"))
    counts = Counter(event.outcome for event in result.activity)
    console.print(
        Text(
            " · ".join(
                f"{counts[word]} {word}"
                for word in (
                    "created",
                    "rewritten",
                    "deleted",
                    "proposed",
                    "failed",
                    "missing",
                )
                if counts[word]
            )
            or (
                "Snapshot activity unavailable"
                if result.completeness == "unsupported"
                else "No snapshot mutations reported"
            )
        )
    )
    for event in result.activity:
        if event.outcome == "accessed":
            continue
        identity = event.object.identity
        label = (
            f"{identity.nodeid} · {identity.key} · {identity.recorder}"
            if identity
            else event.object.storage_key
        )
        console.print(Text(f"  {event.outcome}  {label} → {event.object.target}"))
        if event.reason:
            console.print(Text(f"    {event.reason}"))
    console.print(
        Text(
            f"Lock {result.lock.status} · {len(result.lock.added)} entries added · "
            f"{len(result.lock.removed)} removed"
            if result.lock.status != "unknown"
            else "Lock outcome unknown"
        )
    )
    if result.lock.reason:
        console.print(Text(result.lock.reason))
    if result.reason:
        console.print(Text(result.reason))
    for check in result.checks:
        console.print(Text(f"{check.name}: {check.outcome} · {check.reason}"))
        if check.object:
            owner = check.object.identity
            label = (
                f"{owner.nodeid} · {owner.key} · {owner.recorder}"
                if owner
                else check.object.storage_key
            )
            console.print(Text(f"  {label} → {check.object.target}"))
    for coverage in result.coverage:
        if coverage.status != "checked":
            console.print(
                Text(f"{coverage.target}: {coverage.status} · {coverage.reason}")
            )


def run_standalone(
    flags: tuple[str, ...],
    pytest_args: tuple[str, ...],
    console: Console,
) -> int:
    """Inherit pytest streams; remove private artifacts on every exit path.

    Missing/malformed data leaves snapshot/lock outcomes unknown. The child
    exit status remains authoritative even after partial writes or no handoff.
    """
    errors = Console(stderr=True)
    if any(
        arg == "--ditto-result" or arg.startswith("--ditto-result=")
        for arg in pytest_args
    ):
        errors.print(Text("--ditto-result is reserved for the standalone handoff."))
        return 2
    with tempfile.TemporaryDirectory(prefix="ditto-result-") as directory:
        path = Path(directory) / "result.json"
        try:
            child = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    f"--ditto-result={path}",
                    *flags,
                    *pytest_args,
                ],
                check=False,
            )
        except KeyboardInterrupt:
            errors.print(
                Text(
                    "Interrupted · snapshot and lock outcomes may be incomplete; "
                    "completed writes are not rolled back."
                )
            )
            # Python's subprocess.run waits briefly for the child on Ctrl-C.
            # Consume a handoff if it did finish; never infer absence of writes.
            _consume_result(path, 130, console, errors)
            return 130
        except OSError as exc:
            errors.print(Text(f"Could not launch pytest ({type(exc).__name__})."))
            return 1
        status = child.returncode
        if status < 0:
            status = 128 - status
        _consume_result(path, status, console, errors)
        return status


def _consume_result(
    path: Path,
    status: int,
    console: Console,
    errors: Console,
) -> None:
    try:
        result = decode_result(path.read_bytes())
    except (OSError, ValueError):
        errors.print(
            Text(
                "Ditto result unavailable or malformed · snapshot and lock outcomes "
                "unknown. Completed writes may remain; no rollback is implied."
            )
        )
        return
    if result.tests.exit_code != status:
        errors.print(
            Text(
                "Ditto result does not match the subprocess exit · outcomes may be "
                "incomplete. Completed writes may remain."
            )
        )
        result = replace(
            result,
            tests=replace(result.tests, exit_code=status),
            completeness="incomplete",
            scope_kind="unknown",
            reason="Subprocess status differs from handoff; coverage incomplete",
        )
    render_operation(result, console)
