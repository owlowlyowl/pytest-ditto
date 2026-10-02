"""Subprocess handoff lifecycle and a minimal standalone result consumer.

The shared Rich policy and fuller operation rendering are separate follow-ups.
"""

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


def run_standalone(
    flags: Sequence[str],
    pytest_args: Sequence[str],
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
