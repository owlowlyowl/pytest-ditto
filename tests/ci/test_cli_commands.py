"""Behavioural tests for the new CLI commands: doctor, lint, stats, and exit-code
consistency fixes on list/status/clean/recorders."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from ditto._lockfile import LOCKFILE_VERSION
from ditto._manifest import BackendManifest, ManifestEntry
from ditto.cli import (
    RecorderInfo,
    _doctor_checks,
    _ext_map,
    _find_lint_issues,
    cmd_clean,
    cmd_list,
    cmd_prune,
    cmd_recorders,
    cmd_stats,
    cmd_status,
)


# ── test helpers ──────────────────────────────────────────────────────────────


def _ep(name: str, *, load_raises: Exception | None = None) -> MagicMock:
    """Build a minimal entry-point mock."""
    ep = MagicMock()
    ep.name = name
    if load_raises is not None:
        ep.load.side_effect = load_raises
    else:
        ep.load.return_value = object()
    return ep


def _entry_points(*, pytest11=(), recorders=(), marks=()):
    """Return a side_effect callable for patching importlib.metadata.entry_points."""
    mapping = {
        "pytest11": list(pytest11),
        "ditto_recorders": list(recorders),
        "ditto_marks": list(marks),
    }
    return lambda group: mapping.get(group, [])


@pytest.fixture()
def pickle_ext_map():
    return _ext_map([
        RecorderInfo(name="pickle", extension=".pkl", package="pytest-ditto")
    ])


# ── _doctor_checks: pytest availability ───────────────────────────────────────


def test_pytest_check_passes_when_pytest_is_importable() -> None:
    """The pytest check is marked passing when importlib can locate pytest."""
    with patch(
        "ditto.cli.importlib.metadata.entry_points", side_effect=_entry_points()
    ):
        checks = _doctor_checks()

    result = next(c for c in checks if c.name == "pytest importable")
    assert result.ok is True


def test_pytest_check_fails_when_pytest_is_not_importable() -> None:
    """The pytest check is marked failing when find_spec returns None."""
    with (
        patch("ditto.cli.importlib.util.find_spec", return_value=None),
        patch("ditto.cli.importlib.metadata.entry_points", side_effect=_entry_points()),
    ):
        checks = _doctor_checks()

    result = next(c for c in checks if c.name == "pytest importable")
    assert result.ok is False


# ── _doctor_checks: plugin registration ───────────────────────────────────────


def test_plugin_check_passes_when_ditto_is_in_pytest11() -> None:
    """The plugin check passes when 'ditto' appears in the pytest11 entry points."""
    with patch(
        "ditto.cli.importlib.metadata.entry_points",
        side_effect=_entry_points(pytest11=[_ep("ditto")]),
    ):
        checks = _doctor_checks()

    result = next(c for c in checks if c.name == "ditto plugin registered")
    assert result.ok is True


def test_plugin_check_fails_when_ditto_is_absent_from_pytest11() -> None:
    """The plugin check fails when no 'ditto' entry point is registered under
    pytest11."""
    with patch(
        "ditto.cli.importlib.metadata.entry_points",
        side_effect=_entry_points(pytest11=[]),
    ):
        checks = _doctor_checks()

    result = next(c for c in checks if c.name == "ditto plugin registered")
    assert result.ok is False


# ── _doctor_checks: entry point loading ───────────────────────────────────────


def test_returns_failing_check_with_error_detail_when_recorder_load_raises() -> None:
    """A recorder whose entry point raises on load produces a failing check with the
    error message."""
    bad = _ep("broken_recorder", load_raises=ImportError("missing dep"))
    with patch(
        "ditto.cli.importlib.metadata.entry_points",
        side_effect=_entry_points(recorders=[bad]),
    ):
        checks = _doctor_checks()

    result = next(c for c in checks if c.name == "recorder: broken_recorder")
    assert result.ok is False
    assert "missing dep" in result.detail


def test_returns_failing_check_with_error_detail_when_mark_load_raises() -> None:
    """A mark entry point that raises on load produces a failing check with the
    error message."""
    bad = _ep("broken_mark", load_raises=RuntimeError("oops"))
    with patch(
        "ditto.cli.importlib.metadata.entry_points",
        side_effect=_entry_points(marks=[bad]),
    ):
        checks = _doctor_checks()

    result = next(c for c in checks if c.name == "mark: broken_mark")
    assert result.ok is False
    assert "oops" in result.detail


def test_returns_one_result_per_recorder_entry_point() -> None:
    """Each registered recorder entry point produces exactly one CheckResult."""
    eps = [_ep("pickle"), _ep("yaml"), _ep("json")]
    with patch(
        "ditto.cli.importlib.metadata.entry_points",
        side_effect=_entry_points(recorders=eps),
    ):
        checks = _doctor_checks()

    recorder_checks = [c for c in checks if c.name.startswith("recorder:")]
    assert len(recorder_checks) == 3


def test_returns_one_result_per_mark_entry_point() -> None:
    """Each registered mark entry point produces exactly one CheckResult."""
    eps = [_ep("pickle"), _ep("yaml")]
    with patch(
        "ditto.cli.importlib.metadata.entry_points",
        side_effect=_entry_points(marks=eps),
    ):
        checks = _doctor_checks()

    mark_checks = [c for c in checks if c.name.startswith("mark:")]
    assert len(mark_checks) == 2


# ── _find_lint_issues: clean inputs ───────────────────────────────────────────


def test_returns_no_issues_for_empty_entry_list(pickle_ext_map) -> None:
    """No entries means no issues."""
    assert _find_lint_issues([], pickle_ext_map) == []


def test_returns_no_issues_for_valid_entry(pickle_ext_map) -> None:
    """A well-named, non-empty entry with a known extension produces no issues."""
    entry = ManifestEntry("test_foo@result.pkl", size_bytes=4, modified=None)

    assert _find_lint_issues([entry], pickle_ext_map) == []


# ── _find_lint_issues: issue detection ────────────────────────────────────────


def test_reports_malformed_name_when_key_has_no_at_sign(pickle_ext_map) -> None:
    """A storage key without '@' is flagged as malformed."""
    entry = ManifestEntry("no_at_sign.pkl", size_bytes=4, modified=None)

    issues = _find_lint_issues([entry], pickle_ext_map)

    assert len(issues) == 1
    assert issues[0].filename == "no_at_sign.pkl"
    assert "Malformed" in issues[0].issue


def test_reports_unknown_extension_when_ext_not_in_ext_map() -> None:
    """An entry with an unregistered extension is flagged as unknown format."""
    entry = ManifestEntry("test_foo@result.mystery", size_bytes=4, modified=None)

    issues = _find_lint_issues([entry], {})

    assert len(issues) == 1
    assert "Unknown extension" in issues[0].issue


def test_reports_empty_file_when_size_is_zero(pickle_ext_map) -> None:
    """A zero-byte entry is flagged as empty."""
    entry = ManifestEntry("test_foo@result.pkl", size_bytes=0, modified=None)

    issues = _find_lint_issues([entry], pickle_ext_map)

    assert any(i.issue == "Empty file" for i in issues)


def test_reports_empty_and_unknown_extension_as_separate_issues() -> None:
    """An empty entry with an unknown extension produces two separate issues."""
    entry = ManifestEntry("test_foo@result.mystery", size_bytes=0, modified=None)

    issue_texts = {i.issue for i in _find_lint_issues([entry], {})}

    assert any("Unknown extension" in t for t in issue_texts)
    assert any("Empty file" in t for t in issue_texts)


# ── exit code consistency ─────────────────────────────────────────────────────


def test_list_exits_one_when_no_snapshots_exist(tmp_path) -> None:
    """ditto list exits 1 when the credential-free inventory is empty."""
    result = CliRunner().invoke(cmd_list, [str(tmp_path)])

    assert result.exit_code == 1


def test_status_exits_one_when_no_snapshots_exist(tmp_path) -> None:
    """ditto status exits 1 when the credential-free inventory is empty."""
    result = CliRunner().invoke(cmd_status, [str(tmp_path)])

    assert result.exit_code == 1


def test_clean_exits_one_when_no_ditto_dirs_exist(tmp_path) -> None:
    """ditto clean exits 1 when no .ditto/ directories are found under the given
    path."""
    result = CliRunner().invoke(cmd_clean, [str(tmp_path)])

    assert result.exit_code == 1


def test_recorders_exits_one_when_no_recorders_are_registered() -> None:
    """ditto recorders exits 1 when no recorder entry points are registered."""
    with patch("ditto.cli.importlib.metadata.entry_points", return_value=[]):
        result = CliRunner().invoke(cmd_recorders, [])

    assert result.exit_code == 1


def test_prune_check_forwards_dry_run_flag() -> None:
    """ditto prune --check forwards --ditto-prune-dry-run, not --ditto-prune."""
    with patch("ditto.cli.subprocess.run") as run:
        run.return_value.returncode = 0
        result = CliRunner().invoke(cmd_prune, ["--check"])

    assert result.exit_code == 0
    cmd = run.call_args.args[0]
    assert "--ditto-prune-dry-run" in cmd
    assert "--ditto-prune" not in cmd


def test_prune_without_check_forwards_delete_flag() -> None:
    """Plain ditto prune forwards --ditto-prune (delete)."""
    with patch("ditto.cli.subprocess.run") as run:
        run.return_value.returncode = 0
        result = CliRunner().invoke(cmd_prune, [])

    assert result.exit_code == 0
    cmd = run.call_args.args[0]
    assert "--ditto-prune" in cmd
    assert "--ditto-prune-dry-run" not in cmd


# ── credential-free default + --live opt-in ───────────────────────────────────


def _make_local_snapshot(tmp_path) -> None:
    ditto = tmp_path / ".ditto"
    ditto.mkdir()
    (ditto / "mod.test_a@k.pkl").write_bytes(b"abcd")


def test_list_default_does_not_run_introspect(tmp_path) -> None:
    """The credential-free default `ditto list` never spawns the pytest pass."""
    _make_local_snapshot(tmp_path)
    with patch(
        "ditto._inventory.run_introspect",
        side_effect=AssertionError("must not introspect"),
    ):
        result = CliRunner().invoke(cmd_list, [str(tmp_path)])

    assert result.exit_code == 0
    assert "test_a" in result.output


def test_list_live_runs_introspect(tmp_path) -> None:
    """`ditto list --live` delegates to the introspection pass."""
    manifest = [
        BackendManifest(
            location="redis://h/0",
            entries=[ManifestEntry("mod.test_live@k.pkl", size_bytes=7, modified=None)],
        )
    ]
    with patch("ditto._inventory.run_introspect", return_value=manifest) as run:
        result = CliRunner().invoke(cmd_list, [str(tmp_path), "--live"])

    run.assert_called_once()
    assert result.exit_code == 0
    assert "test_live" in result.output


def test_list_renders_remote_lock_entry_with_dash(tmp_path) -> None:
    """A remote lock entry shows credential-free with an em-dash size."""
    lock = {
        "version": LOCKFILE_VERSION,
        "targets": {
            "redis://localhost:6379/0": {
                "scheme": "redis",
                "entries": [
                    {"nodeid": "test_x.py::test_remote", "key": "k", "recorder": "pkl"}
                ],
            }
        },
    }
    (tmp_path / "ditto.lock").write_text(json.dumps(lock))

    result = CliRunner().invoke(cmd_list, [str(tmp_path)])

    assert result.exit_code == 0
    assert "test_remote" in result.output
    assert "—" in result.output
    assert "size unknown" in result.output  # the remote-unknown note


@pytest.mark.parametrize("command", [cmd_status, cmd_stats])
def test_remote_only_aggregate_renders_unknown_size_as_dash(command, tmp_path) -> None:
    """Remote-only aggregate commands never report unknown bytes as zero."""
    lock = {
        "version": LOCKFILE_VERSION,
        "targets": {
            "redis://localhost:6379/0": {
                "scheme": "redis",
                "entries": [
                    {"nodeid": "test_x.py::test_remote", "key": "k", "recorder": "pkl"}
                ],
            }
        },
    }
    (tmp_path / "ditto.lock").write_text(json.dumps(lock))

    result = CliRunner().invoke(command, [str(tmp_path)])

    assert result.exit_code == 0
    assert "—" in result.output
    assert "0 B" not in result.output


def test_list_hints_when_no_lockfile(tmp_path) -> None:
    """With local snapshots but no ditto.lock, list hints that remotes are hidden."""
    _make_local_snapshot(tmp_path)

    result = CliRunner().invoke(cmd_list, [str(tmp_path)])

    assert result.exit_code == 0
    assert "no ditto.lock found" in result.output
