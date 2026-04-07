"""Behavioural tests for the new CLI commands: doctor, lint, stats, and exit-code
consistency fixes on list/status/clean/recorders."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from ditto.cli import (
    RecorderInfo,
    _doctor_checks,
    _ext_map,
    _find_lint_issues,
    _gather_dir_stats,
    cmd_clean,
    cmd_list,
    cmd_recorders,
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


def _make_ditto_dir(root: Path, subdir: str, files: dict[str, bytes]) -> Path:
    """Create a .ditto/ directory under root/subdir and populate it."""
    d = root / subdir / ".ditto"
    d.mkdir(parents=True)
    for name, content in files.items():
        (d / name).write_bytes(content)
    return d


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
    """The plugin check fails when no 'ditto' entry point is registered under pytest11."""
    with patch(
        "ditto.cli.importlib.metadata.entry_points",
        side_effect=_entry_points(pytest11=[]),
    ):
        checks = _doctor_checks()

    result = next(c for c in checks if c.name == "ditto plugin registered")
    assert result.ok is False


# ── _doctor_checks: entry point loading ───────────────────────────────────────


def test_returns_failing_check_with_error_detail_when_recorder_load_raises() -> None:
    """A recorder whose entry point raises on load produces a failing check with the error message."""
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
    """A mark entry point that raises on load produces a failing check with the error message."""
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


def test_returns_no_issues_for_empty_file_list(pickle_ext_map) -> None:
    """No files means no issues."""
    assert _find_lint_issues([], pickle_ext_map) == []


def test_returns_no_issues_for_valid_snapshot_file(tmp_path, pickle_ext_map) -> None:
    """A correctly named, non-empty file with a known extension produces no issues."""
    fp = tmp_path / "test_foo@result.pkl"
    fp.write_bytes(b"data")

    actual = _find_lint_issues([fp], pickle_ext_map)

    assert actual == []


# ── _find_lint_issues: issue detection ────────────────────────────────────────


def test_reports_malformed_name_when_filename_has_no_at_sign(
    tmp_path, pickle_ext_map
) -> None:
    """A filename without '@' is flagged as malformed."""
    fp = tmp_path / "no_at_sign.pkl"
    fp.write_bytes(b"data")

    issues = _find_lint_issues([fp], pickle_ext_map)

    assert len(issues) == 1
    assert issues[0].filename == "no_at_sign.pkl"
    assert "Malformed" in issues[0].issue


def test_reports_unknown_extension_when_ext_not_in_ext_map(tmp_path) -> None:
    """A snapshot file with an unregistered extension is flagged as unknown format."""
    fp = tmp_path / "test_foo@result.mystery"
    fp.write_bytes(b"data")

    issues = _find_lint_issues([fp], {})

    assert len(issues) == 1
    assert "Unknown extension" in issues[0].issue


def test_reports_empty_file_when_size_is_zero(tmp_path, pickle_ext_map) -> None:
    """A zero-byte snapshot file is flagged as empty."""
    fp = tmp_path / "test_foo@result.pkl"
    fp.write_bytes(b"")

    issues = _find_lint_issues([fp], pickle_ext_map)

    assert any(i.issue == "Empty file" for i in issues)


def test_reports_empty_file_independently_of_unknown_extension(tmp_path) -> None:
    """An empty file with an unknown extension produces two separate issues."""
    fp = tmp_path / "test_foo@result.mystery"
    fp.write_bytes(b"")

    issues = _find_lint_issues([fp], {})

    issue_texts = {i.issue for i in issues}
    assert any("Unknown extension" in t for t in issue_texts)
    assert any("Empty file" in t for t in issue_texts)


# ── _gather_dir_stats ─────────────────────────────────────────────────────────


def test_returns_empty_when_given_no_dirs() -> None:
    """An empty directory list produces no results."""
    assert _gather_dir_stats([], {}) == []


def test_returns_empty_when_all_ditto_dirs_contain_no_files(tmp_path) -> None:
    """A .ditto/ directory with no files is excluded from the results."""
    empty = tmp_path / ".ditto"
    empty.mkdir()

    actual = _gather_dir_stats([empty], {})

    assert actual == []


def test_returns_one_entry_per_non_empty_ditto_dir(tmp_path) -> None:
    """Each .ditto/ directory that contains files produces one entry in the result."""
    dir_a = _make_ditto_dir(tmp_path, "a", {"test@snap.pkl": b"x"})
    dir_b = _make_ditto_dir(tmp_path, "b", {"test@snap.pkl": b"y"})

    actual = _gather_dir_stats([dir_a, dir_b], {})

    assert len(actual) == 2


def test_stats_reflect_file_count_in_directory(tmp_path) -> None:
    """The SnapshotStats for a directory reports the correct number of files."""
    d = _make_ditto_dir(
        tmp_path,
        "tests",
        {
            "test_a@snap.pkl": b"aaa",
            "test_b@snap.pkl": b"bb",
        },
    )

    actual = _gather_dir_stats([d], {})

    _, stats = actual[0]
    assert stats.total_count == 2


def test_skips_empty_dir_and_includes_populated_dir(tmp_path) -> None:
    """An empty .ditto/ dir is skipped while a populated one is included."""
    populated = _make_ditto_dir(tmp_path, "a", {"test@snap.pkl": b"data"})
    empty = tmp_path / "b" / ".ditto"
    empty.mkdir(parents=True)

    actual = _gather_dir_stats([populated, empty], {})

    assert len(actual) == 1
    assert actual[0][0] == populated


# ── exit code consistency ─────────────────────────────────────────────────────


def test_list_exits_one_when_no_snapshot_files_exist(tmp_path) -> None:
    """ditto list exits 1 when no snapshot files are found under the given path."""
    result = CliRunner().invoke(cmd_list, [str(tmp_path)])

    assert result.exit_code == 1


def test_status_exits_one_when_no_snapshot_files_exist(tmp_path) -> None:
    """ditto status exits 1 when no snapshot files are found under the given path."""
    result = CliRunner().invoke(cmd_status, [str(tmp_path)])

    assert result.exit_code == 1


def test_clean_exits_one_when_no_ditto_dirs_exist(tmp_path) -> None:
    """ditto clean exits 1 when no .ditto/ directories are found under the given path."""
    result = CliRunner().invoke(cmd_clean, [str(tmp_path)])

    assert result.exit_code == 1


def test_recorders_exits_one_when_no_recorders_are_registered() -> None:
    """ditto recorders exits 1 when no recorder entry points are registered."""
    with patch("ditto.cli.importlib.metadata.entry_points", return_value=[]):
        result = CliRunner().invoke(cmd_recorders, [])

    assert result.exit_code == 1
