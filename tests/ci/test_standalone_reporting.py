from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from ditto._results import (
    RESULT_VERSION,
    Activity,
    Coverage,
    ObjectRef,
    OperationResult,
    TestResult as RunTests,
    encode_result,
)
from ditto.cli._pytest import cmd_prune, cmd_update
from ditto.cli._result_format import operation_lines


class _FakePytest:
    """Stands in for `subprocess.Popen` of the pytest child.

    It writes `handoff` (if any) to the path in `--ditto-result=`, then its
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
        prefix = "--ditto-result="
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
    with patch("ditto.cli._operation.subprocess.Popen", child):
        return CliRunner().invoke(command, list(args))


def test_prints_legacy_report_when_pytest_runs_directly(
    pytester: pytest.Pytester,
) -> None:
    """Ordinary pytest keeps its existing snapshot report."""
    pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(1, key="x")
    """
    )

    run = pytester.runpytest_subprocess()

    run.assert_outcomes(passed=1)
    assert "ditto snapshot report" in run.stderr.str()
    assert "created" in run.stderr.str()


@pytest.mark.parametrize("payload,status", [(None, 0), (b"not json", 1), (b"{}", 2)])
def test_preserves_child_status_when_handoff_is_unavailable(
    payload: bytes | None, status: int
) -> None:
    """Missing or malformed evidence cannot override the child exit status."""
    child = _FakePytest(status, payload)

    result = _invoke(cmd_update, child, "tests/", "-q")
    actual = result.exit_code
    expected = status

    assert actual == expected
    assert "outcomes unknown" in result.stderr
    assert "No snapshot mutations" not in result.stdout


def test_reports_safe_failure_when_pytest_cannot_launch() -> None:
    """Launch errors report failure without copying exception secrets."""
    with patch("ditto.cli._operation.subprocess.Popen", side_effect=OSError("secret")):
        result = CliRunner().invoke(cmd_update)
    actual = result.exit_code
    expected = 1

    assert actual == expected
    assert "Could not launch pytest" in result.stderr
    assert "secret" not in result.output


def test_prints_one_report_when_standalone_update_completes(
    pytester: pytest.Pytester,
) -> None:
    """Standalone update prints one snapshot report alongside pytest output."""
    pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(1, key="[bold]x")
    """
    )

    run = pytester.run(
        sys.executable,
        "-c",
        "from ditto.cli import cli; cli()",
        "update",
        "-q",
    )
    actual = (
        run.ret,
        run.stdout.str().count("Ditto report"),
    )
    expected = (
        0,
        1,
    )

    assert actual == expected
    assert "1 passed" in run.stdout.str()
    assert "1 created" in run.stdout.str()
    assert "[bold]x" in run.stdout.str()
    assert "ditto snapshot report" not in run.stderr.str()


def test_preserves_pytest_failure_when_handoff_cannot_be_written(
    pytester: pytest.Pytester,
) -> None:
    """Failure to publish evidence never masks the pytest outcome."""
    pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(1, key="x")
            assert False
    """
    )

    run = pytester.runpytest_subprocess(
        f"--ditto-result={pytester.path / 'missing-dir' / 'result.json'}",
    )

    run.assert_outcomes(failed=1)
    assert "standalone result unavailable" in run.stderr.str()
    assert not (pytester.path / "missing-dir").exists()


def test_reports_actual_failure_when_handoff_exit_status_is_stale() -> None:
    """The subprocess status overrides stale successful evidence."""
    result_data = OperationResult(
        RESULT_VERSION,
        "/project",
        RunTests(0),
        (Activity(ObjectRef("local", "x.json"), "created", "write"),),
        completeness="complete",
        scope_kind="full",
    )

    child = _FakePytest(1, encode_result(result_data))

    result = _invoke(cmd_update, child)
    actual = result.exit_code
    expected = 1

    assert actual == expected
    assert "does not match" in result.stderr
    assert "pytest exit 1" in result.stdout
    assert "Scope unknown" in result.stdout
    assert "1 created" in result.stdout


def test_reports_exact_missing_key_when_standalone_verify_detects_drift(
    pytester: pytest.Pytester,
) -> None:
    """Standalone verification reports the exact missing identity once."""
    pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(1, key="[bold]missing:key")
    """
    )
    pytester.runpytest_subprocess().assert_outcomes(passed=1)
    (stored,) = (pytester.path / ".ditto").iterdir()
    stored.unlink()

    run = pytester.run(
        sys.executable, "-c", "from ditto.cli import cli; cli()", "verify", "-q"
    )
    actual = (
        run.ret,
        run.stdout.str().count("Ditto report"),
    )
    expected = (
        1,
        1,
    )

    assert actual == expected
    assert "[bold]missing:key" in run.stdout.str()
    assert "missing: failed" in run.stdout.str()
    assert "lock drift detected" not in run.stdout.str()
    assert not stored.exists()


@pytest.mark.parametrize("status", [0, 1, -15])
def test_removes_private_artifacts_when_subprocess_exits(status: int) -> None:
    """Private handoff files disappear after success, failure, or a signal."""
    child = _FakePytest(status, b"malformed")

    _invoke(cmd_update, child)

    assert not child.handoff_path().parent.exists()


@pytest.mark.parametrize(
    "location,arguments,remains",
    [
        ("local", ["--check"], True),
        ("local", [], False),
        ("shared", [], True),
        ("shared", ["--shared"], False),
    ],
)
def test_retains_orphan_only_when_prune_policy_requires_it(
    pytester: pytest.Pytester,
    tmp_path: Path,
    location: str,
    arguments: Sequence[str],
    remains: bool,
) -> None:
    """CLI prune respects dry runs and consent for shared targets."""
    targets = {"shared": tmp_path / "shared", "local": pytester.path / "local"}
    target = targets[location]
    target.mkdir()
    pytester.makeini(f"[pytest]\nditto_target = file://{target}")
    pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(1, key="current")
    """
    )
    pytester.runpytest_subprocess().assert_outcomes(passed=1)
    orphan = target / "test_orders.old@a.json"
    orphan.write_text("1")

    run = pytester.run(
        sys.executable,
        "-c",
        "from ditto.cli import cli; cli()",
        "prune",
        *arguments,
        "-q",
    )
    actual = orphan.exists()

    expected = remains
    assert actual == expected
    run.assert_outcomes(passed=1)


def test_shows_lock_parse_error_when_standalone_verify_cannot_read_lock(
    pytester: pytest.Pytester,
) -> None:
    """Standalone verify keeps the diagnostic that says how the lock is broken."""
    pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(1, key="x")
    """
    )
    pytester.runpytest_subprocess().assert_outcomes(passed=1)
    (pytester.path / "ditto.lock").write_text("{not json")

    run = pytester.run(
        sys.executable, "-c", "from ditto.cli import cli; cli()", "verify", "-q"
    )

    assert "JSON is malformed" in run.stdout.str()


def test_shows_failed_deletion_reason_when_collecting_results(
    pytester: pytest.Pytester,
) -> None:
    """A failed deletion's reason reaches the terminal but not the handoff file."""
    pytester.makeconftest("""
        from ditto.backends import FsspecMapping
        def delete(self, key):
            raise PermissionError("bucket is read-only")
        FsspecMapping.__delitem__ = delete
    """)
    pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(1, key="x")
    """
    )
    pytester.runpytest_subprocess().assert_outcomes(passed=1)
    (pytester.path / ".ditto" / "test_orders.old@a.json").write_text("1")
    handoff = pytester.path / "result.json"

    run = pytester.runpytest_subprocess("--ditto-prune", f"--ditto-result={handoff}")

    assert "bucket is read-only" in run.stdout.str()
    assert "bucket is read-only" not in handoff.read_text()


def test_lets_pytest_finish_when_interrupted_once() -> None:
    """A first Ctrl-C waits for pytest to finish its session rather than kill it."""
    child = _FakePytest(2, interrupts=1)

    result = _invoke(cmd_update, child)
    actual = (result.exit_code, child.killed)

    expected = (2, False)
    assert actual == expected


def test_kills_pytest_when_interrupted_twice() -> None:
    """A second Ctrl-C stops pytest and reports the outcome as unknown."""
    child = _FakePytest(2, interrupts=2)

    result = _invoke(cmd_update, child)
    actual = (result.exit_code, child.killed)

    expected = (130, True)
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


def test_omits_unchecked_targets_when_rendering_report() -> None:
    """The report names failed targets, not every target it didn't inspect."""
    result = OperationResult(
        RESULT_VERSION,
        "/project",
        RunTests(0),
        coverage=(
            Coverage("unread", "runtime", "unchecked", "Not enumerated"),
            Coverage("broken", "live", "failed", "OSError inspecting target"),
        ),
    )

    lines = operation_lines(result)
    actual = [line for line in lines if "unread" in line or "broken" in line]

    expected = ["broken: failed · OSError inspecting target"]
    assert actual == expected
