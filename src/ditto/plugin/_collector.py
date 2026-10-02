"""What a session gathers for `--ditto-result`, and only when it was asked for."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from ditto._lockfile import LockFile
from ditto._result_policy import LockProblem
from ditto._results import (
    Activity,
    Check,
    Coverage,
    CoverageStatus,
    Provenance,
    TestPhase,
)


__all__ = ("ResultCollector",)


@dataclass
class ResultCollector:
    """Evidence for the standalone handoff, gathered while the session runs.

    Targets are kept unmasked so distinct targets stay distinct; the handoff
    masks them once, when it's written. Snapshot calls are recorded on the
    session tracker's `events`, which is switched on alongside this.
    """

    path: Path
    lock_before: LockFile | None = None
    lock_before_error: str | None = None
    lock_problem: LockProblem | None = None
    # Keyed by unmasked target id: a target inspected twice keeps its last outcome.
    coverage: dict[str, Coverage] = field(default_factory=dict)
    checks: list[Check] = field(default_factory=list)
    # Prune outcomes; snapshot calls are on the tracker.
    activity: list[Activity] = field(default_factory=list)
    phases: list[TestPhase] = field(default_factory=list)
    # pytest's code for an exception that escaped session finish, which leaves
    # `session.exitstatus` stale.
    exit_override: pytest.ExitCode | None = None

    def cover(
        self,
        target: str,
        source: Provenance,
        status: CoverageStatus,
        reason: str | None = None,
    ) -> None:
        """Record how far `target` was inspected."""
        self.coverage[target] = Coverage(target, source, status, reason)
