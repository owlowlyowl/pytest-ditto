"""Run pytest for a standalone command, then report what its handoff says."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from rich.console import Console
from rich.text import Text

from ditto._handoff import Handoff, Outcome, read_handoff


__all__ = ("handoff_lines", "run_standalone")


_HANDOFF_OPTION = "--ditto-handoff"

# Outcomes in the order the summary counts them.
_OUTCOMES = (
    "created",
    "rewritten",
    "write_failed",
    "deleted",
    "delete_failed",
    "would_delete",
)


def _label(outcome: Outcome) -> str:
    """The snapshot's identity when it's known, else its storage key."""
    ref = outcome.snapshot
    if ref.nodeid is None:
        return ref.storage_key
    return f"{ref.nodeid} · {ref.key} · {ref.recorder}"


def handoff_lines(handoff: Handoff) -> list[str]:
    """The report's lines: a count of each outcome, each snapshot, the lock."""
    counts = Counter(outcome.outcome for outcome in handoff.outcomes)
    summary = " · ".join(
        f"{counts[name]} {name.replace('_', ' ')}" for name in _OUTCOMES if counts[name]
    )
    lock = handoff.lock
    return [
        f"Ditto · {summary or 'no snapshot changes'}",
        *(
            f"  {o.outcome.replace('_', ' ')}  {_label(o)} → {o.snapshot.target}"
            for o in handoff.outcomes
        ),
        f"Lock {lock.status} · {lock.added} added · {lock.removed} removed"
        if lock.status == "written"
        else f"Lock {lock.status}",
    ]


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
    """Run pytest with `flags`, print the Ditto report, and return pytest's status.

    pytest's own output passes straight through. The handoff lives in a private
    temporary directory removed on every exit path. Without a readable handoff
    the outcomes are reported as unknown, never as no changes.
    """
    if any(a.split("=", 1)[0] == _HANDOFF_OPTION for a in pytest_args):
        errors.print(Text(f"{_HANDOFF_OPTION} is set by ditto; don't pass it."))
        return 2
    with tempfile.TemporaryDirectory(prefix="ditto-handoff-") as directory:
        path = Path(directory) / "handoff.json"
        command = [
            sys.executable,
            "-m",
            "pytest",
            f"{_HANDOFF_OPTION}={path}",
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
        if status < 0:
            status = 128 - status  # killed by a signal, as a shell reports it
        if interrupted:
            errors.print(
                Text(
                    "Interrupted · pytest finished its session; completed "
                    "writes are not rolled back."
                )
            )
        try:
            handoff = read_handoff(path)
        except (OSError, ValueError):
            errors.print(
                Text(
                    "pytest didn't report Ditto's outcomes · snapshot and lock "
                    "outcomes unknown; completed writes are not rolled back."
                )
            )
            return status
        for line in handoff_lines(handoff):
            console.print(Text(line))
        return status
