"""Run pytest, consume its private result handoff, and render a standalone report."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from rich.console import Console
from rich.text import Text

from ditto._result_io import read_result
from ditto._result_policy import reconcile_exit
from ditto._results import OperationResult

from ._result_format import operation_lines


def render_operation(result: OperationResult, console: Console) -> None:
    """Emit literal report text through the supplied console."""
    for line in operation_lines(result):
        console.print(Text(line))


def _wait_for_pytest(command: list[str]) -> tuple[int, bool]:
    """Run pytest to completion; return its exit status and whether Ctrl-C was hit.

    Ctrl-C reaches pytest too, which then finishes its session: the lock write,
    any deletions, and the handoff. So a first Ctrl-C keeps waiting for it,
    where `subprocess.run` would kill it a moment later, mid-write. A second
    Ctrl-C kills it and propagates.
    """
    child = subprocess.Popen(command)
    interrupted = False
    while True:
        try:
            return child.wait(), interrupted
        except KeyboardInterrupt:
            if interrupted:
                child.kill()
                child.wait()
                raise
            interrupted = True


def run_standalone(
    flags: Sequence[str],
    pytest_args: Sequence[str],
    console: Console,
    errors: Console,
) -> int:
    """Inherit pytest streams; remove private artifacts on every exit path.

    Missing/malformed data leaves snapshot/lock outcomes unknown. The child
    exit status remains authoritative even after partial writes or no handoff.
    """
    if any(
        arg == "--ditto-result" or arg.startswith("--ditto-result=")
        for arg in pytest_args
    ):
        errors.print(Text("--ditto-result is reserved for the standalone handoff."))
        return 2
    with tempfile.TemporaryDirectory(prefix="ditto-result-") as directory:
        path = Path(directory) / "result.json"
        command = [
            sys.executable,
            "-m",
            "pytest",
            f"--ditto-result={path}",
            *flags,
            *pytest_args,
        ]
        try:
            status, interrupted = _wait_for_pytest(command)
        except KeyboardInterrupt:
            errors.print(
                Text(
                    "Stopped pytest · snapshot and lock outcomes unknown; "
                    "completed writes are not rolled back."
                )
            )
            return 130
        except OSError as exc:
            errors.print(Text(f"Could not launch pytest ({type(exc).__name__})."))
            return 1
        if interrupted:
            errors.print(
                Text(
                    "Interrupted · pytest finished its session; the report shows "
                    "what completed, and completed writes are not rolled back."
                )
            )
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
        result = read_result(path)
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
    render_operation(reconcile_exit(result, status), console)
