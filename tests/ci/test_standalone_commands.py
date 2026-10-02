"""How standalone `ditto run/update/lock/prune` run pytest and report its handoff."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from ditto._handoff import (
    HANDOFF_VERSION,
    Handoff,
    LockOutcome,
    Outcome,
    SnapshotRef,
    encode_handoff,
)
from ditto.cli._pytest import cmd_lock, cmd_prune, cmd_update
from ditto.cli._standalone import handoff_lines


class _FakePytest:
    """Stands in for `subprocess.Popen` of the pytest child.

    It writes `handoff` (if any) to the path in `--ditto-handoff=`, then its
    `wait` raises KeyboardInterrupt `interrupts` times before returning `status`.
    """

    def __init__(
        self, status: int, handoff: bytes | None = None, interrupts: int = 0
    ) -> None:
        self.status = status
        self.handoff = handoff
        self.interrupts = interrupts
        self.command: list[str] = []
        self.killed = False

    def __call__(self, command: list[str]) -> _FakePytest:
        self.command = command
        if self.handoff is not None:
            self.handoff_path().write_bytes(self.handoff)
        return self

    def handoff_path(self) -> Path:
        prefix = "--ditto-handoff="
        (flag,) = [a for a in self.command if a.startswith(prefix)]
        return Path(flag.removeprefix(prefix))

    def wait(self) -> int:
        if self.interrupts:
            self.interrupts -= 1
            raise KeyboardInterrupt
        return self.status

    def kill(self) -> None:
        self.killed = True


def _invoke(command, child: _FakePytest, *args: str):
    with patch("ditto.cli._standalone.subprocess.Popen", child):
        return CliRunner().invoke(command, list(args))


_CREATED = encode_handoff(
    Handoff(
        HANDOFF_VERSION,
        (
            Outcome(
                SnapshotRef(".ditto", "t.test_a@x.json", "t.py::test_a", "x", "json"),
                "created",
            ),
        ),
        LockOutcome("written", added=1),
    )
)


def test_reports_created_snapshot_when_standalone_update_runs(
    pytester: pytest.Pytester,
) -> None:
    """Standalone update prints one Ditto report naming the snapshot it wrote."""
    pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(1, key="[bold]x")
    """
    )

    run = pytester.run(
        sys.executable, "-c", "from ditto.cli import cli; cli()", "update", "-q"
    )

    assert run.ret == 0
    assert "created  test_orders.py::test_snapshot · [bold]x · json" in run.stdout.str()
    assert "ditto snapshot report" not in run.stderr.str()


@pytest.mark.parametrize("status", [0, 1, 3])
def test_exits_with_pytest_status_when_handoff_is_read(status: int) -> None:
    """The command's exit status is always pytest's."""
    child = _FakePytest(status, _CREATED)

    result = _invoke(cmd_update, child)
    actual = result.exit_code

    expected = status
    assert actual == expected


@pytest.mark.parametrize("handoff", [None, b"not json"])
def test_reports_outcomes_unknown_when_handoff_is_unreadable(
    handoff: bytes | None,
) -> None:
    """A missing or malformed handoff is reported as unknown, not as no changes."""
    child = _FakePytest(0, handoff)

    result = _invoke(cmd_update, child)

    assert "outcomes unknown" in result.stderr


def test_reports_signal_exit_status_when_pytest_is_killed() -> None:
    """A child killed by a signal exits the way a shell reports it, 128 + signal."""
    child = _FakePytest(-15)

    result = _invoke(cmd_update, child)
    actual = result.exit_code

    expected = 143
    assert actual == expected


def test_reports_launch_failure_without_exception_text() -> None:
    """A launch failure names the error type, not its message."""
    with patch("ditto.cli._standalone.subprocess.Popen", side_effect=OSError("secret")):
        result = CliRunner().invoke(cmd_update)
    actual = (result.exit_code, "secret" in result.output)

    expected = (1, False)
    assert actual == expected


@pytest.mark.parametrize("status", [0, 1, -15])
def test_removes_handoff_when_pytest_exits(status: int) -> None:
    """The private handoff directory is gone once the command finishes."""
    child = _FakePytest(status, _CREATED)

    _invoke(cmd_update, child)

    assert not child.handoff_path().parent.exists()


def test_lets_pytest_finish_when_interrupted_once() -> None:
    """A first Ctrl-C waits for pytest to finish its session rather than kill it."""
    child = _FakePytest(2, interrupts=1)

    result = _invoke(cmd_update, child)
    actual = (result.exit_code, child.killed)

    expected = (2, False)
    assert actual == expected


def test_kills_pytest_when_interrupted_twice() -> None:
    """A second Ctrl-C stops pytest and exits as interrupted."""
    child = _FakePytest(2, interrupts=2)

    result = _invoke(cmd_update, child)
    actual = (result.exit_code, child.killed)

    expected = (130, True)
    assert actual == expected


def test_refuses_handoff_option_when_user_passes_it() -> None:
    """--ditto-handoff belongs to the CLI, so a user can't redirect it."""
    child = _FakePytest(0)

    result = _invoke(cmd_lock, child, "--ditto-handoff=elsewhere.json")
    actual = (result.exit_code, child.command)

    expected = (2, [])
    assert actual == expected


@pytest.mark.parametrize(
    "arguments,flags",
    [
        ([], ["--ditto-prune"]),
        (["--check"], ["--ditto-prune-dry-run"]),
        (["--shared"], ["--ditto-prune", "--ditto-prune-shared"]),
    ],
)
def test_forwards_prune_flags_when_prune_options_are_given(
    arguments: list[str], flags: list[str]
) -> None:
    """ditto prune's options map onto the pytest prune flags it forwards."""
    child = _FakePytest(0)

    _invoke(cmd_prune, child, *arguments)
    actual = [a for a in child.command if a.startswith("--ditto-prune")]

    expected = flags
    assert actual == expected


def test_lists_deletion_by_storage_key_when_owner_is_unknown() -> None:
    """An orphan has no recorded identity, so the report names its storage key."""
    handoff = Handoff(
        HANDOFF_VERSION,
        (Outcome(SnapshotRef("s3://bucket", "t.old@a.json"), "deleted"),),
    )

    actual = handoff_lines(handoff)

    expected = [
        "Ditto · 1 deleted",
        "  deleted  t.old@a.json → s3://bucket",
        "Lock unchanged",
    ]
    assert actual == expected


def test_says_so_when_run_changed_nothing() -> None:
    """A run with no snapshot or lock changes says so rather than printing nothing."""
    actual = handoff_lines(Handoff(HANDOFF_VERSION))

    expected = ["Ditto · no snapshot changes", "Lock unchanged"]
    assert actual == expected
