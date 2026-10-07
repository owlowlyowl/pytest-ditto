"""Behavioural tests for the new CLI commands: doctor, lint, stats, and exit-code
consistency fixes on list/status/clean/recorders."""

from __future__ import annotations

import importlib.metadata
import json
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from rich.console import Console

from ditto._lockfile import LOCKFILE_VERSION
from ditto._manifest import BackendManifest, ManifestEntry
from ditto.backends import BackendRegistry
from ditto.recorders import RecorderRegistry
from ditto.cli._data import RecorderInfo, _ext_map
from ditto.cli._diagnostics import (
    _backend_checks,
    _doctor_checks,
    _find_lint_issues,
    _recorder_checks,
)
from ditto.cli._inventory import cmd_list, cmd_stats, cmd_status
from ditto.cli._maintenance import cmd_clean, cmd_recorders
from ditto.cli._pytest import cmd_prune


# ── test helpers ──────────────────────────────────────────────────────────────


def _ep(
    name: str,
    *,
    value: str = "some_package.module",
    load_raises: Exception | None = None,
) -> MagicMock:
    """Build a minimal entry-point mock."""
    ep = MagicMock()
    ep.name = name
    ep.value = value
    if load_raises is not None:
        ep.load.side_effect = load_raises
    else:
        ep.load.return_value = object()
    return ep


def _entry_points(*, pytest11=(), recorders=()):
    """Return a side_effect callable for patching importlib.metadata.entry_points."""
    mapping = {
        "pytest11": list(pytest11),
        "ditto_recorders": list(recorders),
    }
    return lambda group: mapping.get(group, [])


@pytest.fixture()
def json_ext_map():
    return _ext_map([
        RecorderInfo(name="json", identifier=".json", package="pytest-ditto")
    ])


# ── _doctor_checks: pytest availability ───────────────────────────────────────


def test_pytest_check_passes_when_pytest_is_importable() -> None:
    """The pytest check is marked passing when importlib can locate pytest."""
    with patch(
        "ditto.cli._diagnostics.importlib.metadata.entry_points",
        side_effect=_entry_points(),
    ):
        checks = _doctor_checks()

    result = next(c for c in checks if c.name == "pytest importable")
    assert result.ok is True


def test_pytest_check_fails_when_pytest_is_not_importable() -> None:
    """The pytest check is marked failing when find_spec returns None."""
    with (
        patch("ditto.cli._diagnostics.importlib.util.find_spec", return_value=None),
        patch(
            "ditto.cli._diagnostics.importlib.metadata.entry_points",
            side_effect=_entry_points(),
        ),
    ):
        checks = _doctor_checks()

    result = next(c for c in checks if c.name == "pytest importable")
    assert result.ok is False


# ── _doctor_checks: plugin registration ───────────────────────────────────────


def _plugin_check(*pytest11: MagicMock):
    with patch(
        "ditto.cli._diagnostics.importlib.metadata.entry_points",
        side_effect=_entry_points(pytest11=pytest11),
    ):
        checks = _doctor_checks()
    return next(c for c in checks if c.name == "ditto plugin registered")


def test_plugin_check_passes_when_an_entry_point_targets_the_plugin_module() -> None:
    """The plugin check passes when a pytest11 entry point targets ditto.plugin."""
    result = _plugin_check(_ep("ditto", value="ditto.plugin"))

    assert result.ok is True


def test_plugin_check_identifies_the_plugin_by_module_not_by_name() -> None:
    """The check matches the entry point's target module, so it is independent of
    the name the entry point is registered under."""
    result = _plugin_check(_ep("any_name", value="ditto.plugin"))

    assert result.ok is True


def test_plugin_check_fails_when_no_entry_point_targets_the_plugin_module() -> None:
    """The plugin check fails, naming the missing module, when no pytest11 entry
    point targets ditto.plugin — even if one is named 'ditto'."""
    result = _plugin_check(_ep("ditto", value="someone_else.plugin"))

    assert result.ok is False
    assert "ditto.plugin" in result.detail


def test_plugin_check_fails_when_plugin_module_cannot_be_imported() -> None:
    """The plugin check fails with the import error when ditto.plugin is
    registered but cannot be loaded."""
    result = _plugin_check(
        _ep("ditto", value="ditto.plugin", load_raises=ImportError("missing dep"))
    )

    assert result.ok is False
    assert "missing dep" in result.detail


def test_plugin_check_fails_when_another_plugin_claims_the_same_name() -> None:
    """pytest registers only the first plugin under a given name and silently skips
    the rest, so a name clash is reported as a failure naming the other plugin."""
    result = _plugin_check(
        _ep("ditto", value="ditto.plugin"),
        _ep("ditto", value="other_package.plugin"),
    )

    assert result.ok is False
    assert "other_package.plugin" in result.detail


def test_installed_package_registers_the_plugin_under_the_name_ditto() -> None:
    """The installed distribution registers ditto.plugin as the pytest11 entry
    point 'ditto', so `-p no:ditto` disables it and `doctor` passes for real."""
    pytest11 = importlib.metadata.distribution("pytest-ditto").entry_points.select(
        group="pytest11"
    )

    assert [(ep.name, ep.value) for ep in pytest11] == [("ditto", "ditto.plugin")]


def test_doctor_plugin_check_passes_against_the_real_installation() -> None:
    """Against the real installed metadata (no mocks), the plugin check passes."""
    result = next(c for c in _doctor_checks() if c.name == "ditto plugin registered")

    assert result.ok is True, result.detail


# ── _doctor_checks: entry point loading ───────────────────────────────────────


def test_returns_failing_check_with_error_detail_when_recorder_load_raises(
    make_distribution,
) -> None:
    """A recorder whose entry point fails to load gets a failing check with the
    error."""
    eps = make_distribution(
        "plug", "1.0", {"ditto_recorders": {"broken": "ditto_no_such_module:x"}}
    )

    checks = _recorder_checks(RecorderRegistry(eps, []))

    result = next(c for c in checks if c.name == "recorder: broken")
    assert result.ok is False
    assert "ditto_no_such_module" in result.detail


def test_returns_one_passing_result_per_loadable_recorder(make_distribution) -> None:
    """Each recorder that loads produces exactly one passing check."""
    eps = make_distribution(
        "plug",
        "1.0",
        {
            "ditto_recorders": {
                "json": "ditto.recorders._json:json",
                "yaml": "ditto.recorders._yaml:yaml",
            }
        },
    )

    checks = _recorder_checks(RecorderRegistry(eps, []))

    actual = [(c.name, c.ok) for c in checks]
    expected = [("recorder: json", True), ("recorder: yaml", True)]
    assert actual == expected


def test_reports_a_contract_problem_once_instead_of_per_recorder(
    make_distribution,
) -> None:
    """A duplicated name fails one contract check, naming both distributions."""
    json_ep = "ditto.recorders._json:json"
    first = make_distribution("plug-a", "1.0", {"ditto_recorders": {"fmt": json_ep}})
    second = make_distribution("plug-b", "2.0", {"ditto_recorders": {"fmt": json_ep}})

    checks = _recorder_checks(RecorderRegistry([*first, *second], []))

    (check,) = checks
    assert (check.name, check.ok) == ("plugin contract", False)
    assert "plug-a 1.0, plug-b 2.0" in check.detail


def test_accepts_aliases_alongside_other_recorders(make_distribution) -> None:
    """Two names for one recorder and a third recorder all pass doctor."""
    eps = make_distribution(
        "plug",
        "1.0",
        {
            "ditto_recorders": {
                "json": "ditto.recorders._json:json",
                "json_alias": "ditto.recorders._json:json",
                "yaml": "ditto.recorders._yaml:yaml",
            }
        },
    )

    checks = _recorder_checks(RecorderRegistry(eps, []))

    assert all(c.ok for c in checks)


# ── _find_lint_issues: clean inputs ───────────────────────────────────────────


def test_returns_no_issues_for_empty_entry_list(json_ext_map) -> None:
    """No entries means no issues."""
    assert _find_lint_issues([], json_ext_map) == []


def test_returns_no_issues_for_valid_entry(json_ext_map) -> None:
    """A well-named, non-empty entry with a known extension produces no issues."""
    entry = ManifestEntry(
        "test_foo@result~0000000000000000.json", size_bytes=4, modified=None
    )

    assert _find_lint_issues([entry], json_ext_map) == []


# ── _find_lint_issues: issue detection ────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "no_at_sign.json",
        "test_foo@result.json",
        "garbage~0123456789abcdef.json",
        "~0123456789abcdef.json",
    ],
    ids=["no-at-sign", "unhashed-2.0.0b1-name", "hash-without-at", "hash-only"],
)
def test_reports_a_name_not_in_the_stored_form(json_ext_map, name) -> None:
    """A name not in the `<test>@<key>~<hash>.<recorder>` form is flagged,
    including one stored before names were hashed and one with a hash but no
    `@`."""
    entry = ManifestEntry(name, size_bytes=4, modified=None)

    issues = _find_lint_issues([entry], json_ext_map)

    assert len(issues) == 1
    assert issues[0].filename == name
    assert "Malformed" in issues[0].issue


def test_reports_unknown_identifier_when_not_in_identifier_map() -> None:
    """An entry with an unregistered recorder identifier is flagged."""
    entry = ManifestEntry(
        "test_foo@result~0000000000000000.mystery", size_bytes=4, modified=None
    )

    issues = _find_lint_issues([entry], {})

    assert len(issues) == 1
    assert "Unknown recorder identifier" in issues[0].issue


def test_reports_empty_file_when_size_is_zero(json_ext_map) -> None:
    """A zero-byte entry is flagged as empty."""
    entry = ManifestEntry(
        "test_foo@result~0000000000000000.json", size_bytes=0, modified=None
    )

    issues = _find_lint_issues([entry], json_ext_map)

    assert any(i.issue == "Empty file" for i in issues)


def test_reports_empty_and_unknown_extension_as_separate_issues() -> None:
    """An empty entry with an unknown extension produces two separate issues."""
    entry = ManifestEntry(
        "test_foo@result~0000000000000000.mystery", size_bytes=0, modified=None
    )

    issue_texts = {i.issue for i in _find_lint_issues([entry], {})}

    assert any("Unknown recorder identifier" in t for t in issue_texts)
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


def test_inventory_command_prints_to_the_console_given_as_the_context_object(
    tmp_path,
) -> None:
    """An inventory command writes to the Console passed as Click's context object."""
    buffer = StringIO()

    CliRunner().invoke(cmd_status, [str(tmp_path)], obj=Console(file=buffer))

    assert "No snapshot files found." in buffer.getvalue()


def test_maintenance_command_prints_to_the_console_given_as_the_context_object(
    tmp_path,
) -> None:
    """A maintenance command writes to the Console passed as Click's context
    object."""
    buffer = StringIO()

    CliRunner().invoke(cmd_clean, [str(tmp_path)], obj=Console(file=buffer))

    assert "No .ditto/ directories found" in buffer.getvalue()


def test_recorders_exits_one_when_no_recorders_are_registered() -> None:
    """ditto recorders exits 1 when no recorder entry points are registered."""
    with patch("ditto.cli._data.importlib.metadata.entry_points", return_value=[]):
        result = CliRunner().invoke(cmd_recorders, [])

    assert result.exit_code == 1


def test_prune_check_forwards_dry_run_flag() -> None:
    """ditto prune --check forwards --ditto-prune-dry-run, not --ditto-prune."""
    with patch("ditto.cli._pytest.subprocess.run") as run:
        run.return_value.returncode = 0
        result = CliRunner().invoke(cmd_prune, ["--check"])

    assert result.exit_code == 0
    cmd = run.call_args.args[0]
    assert "--ditto-prune-dry-run" in cmd
    assert "--ditto-prune" not in cmd


def test_prune_without_check_forwards_delete_flag() -> None:
    """Plain ditto prune forwards --ditto-prune (delete)."""
    with patch("ditto.cli._pytest.subprocess.run") as run:
        run.return_value.returncode = 0
        result = CliRunner().invoke(cmd_prune, [])

    assert result.exit_code == 0
    cmd = run.call_args.args[0]
    assert "--ditto-prune" in cmd
    assert "--ditto-prune-dry-run" not in cmd


def test_prune_shared_forwards_prune_shared_flag() -> None:
    """ditto prune --shared forwards --ditto-prune-shared with --ditto-prune."""
    with patch("ditto.cli._pytest.subprocess.run") as run:
        run.return_value.returncode = 0
        result = CliRunner().invoke(cmd_prune, ["--shared"])

    assert result.exit_code == 0
    cmd = run.call_args.args[0]
    assert "--ditto-prune" in cmd
    assert "--ditto-prune-shared" in cmd


# ── credential-free default + --live opt-in ───────────────────────────────────


def _make_local_snapshot(tmp_path) -> None:
    ditto = tmp_path / ".ditto"
    ditto.mkdir()
    (ditto / "mod.test_a@k.json").write_bytes(b"abcd")


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


def test_list_shows_the_lock_s_test_and_key_and_marks_names_it_lacks(
    pytester,
) -> None:
    """A name's label replaces `:`; `ditto list` shows the exact node id and key
    from the lock instead, and marks a file the lock doesn't record."""
    pytester.makepyfile(
        test_mod="""
        import pytest

        @pytest.mark.parametrize("t", ["12:00"])
        def test_get(snapshot, t):
            snapshot(t, key="body:raw")
        """
    )
    pytester.runpytest_subprocess().assert_outcomes(passed=1)
    orphan_name = "test_mod.test_old@v~0123abcd0123abcd.json"
    (pytester.path / ".ditto" / orphan_name).write_text("1")

    result = CliRunner().invoke(cmd_list, [str(pytester.path)], obj=Console(width=200))

    assert result.exit_code == 0, result.output
    locked = next(line for line in result.output.splitlines() if "test_get" in line)
    assert "test_mod.py::test_get[12:00]" in locked
    assert "body:raw" in locked
    orphan = next(line for line in result.output.splitlines() if "test_old" in line)
    assert "test_mod.test_old" in orphan
    assert "not in lock" in orphan


def test_list_shows_a_bracketed_key_literally(pytester) -> None:
    """A key that looks like Rich markup is shown as written, not parsed."""
    pytester.makepyfile(
        test_mod="""
        def test_t(snapshot):
            snapshot(1, key="[/]")
            snapshot(2, key="[bold]x")
        """
    )
    pytester.runpytest_subprocess().assert_outcomes(passed=1)

    result = CliRunner().invoke(cmd_list, [str(pytester.path)], obj=Console(width=200))

    assert result.exit_code == 0, result.output
    assert "[/]" in result.output
    assert "[bold]x" in result.output


def test_list_checks_the_lock_per_target(pytester) -> None:
    """A file named like a locked snapshot, but under another target, is marked
    as not in the lock."""
    pytester.makepyfile(
        test_mod="""
        def test_t(snapshot):
            snapshot(1, key="k")
        """
    )
    pytester.runpytest_subprocess().assert_outcomes(passed=1)
    (locked,) = (pytester.path / ".ditto").iterdir()
    other = pytester.mkdir("other") / ".ditto"
    other.mkdir()
    (other / locked.name).write_bytes(locked.read_bytes())

    result = CliRunner().invoke(cmd_list, [str(pytester.path)], obj=Console(width=200))

    assert result.exit_code == 0, result.output
    rows = [line for line in result.output.splitlines() if "test_t" in line]
    assert len(rows) == 2
    assert sum("not in lock" in row for row in rows) == 1
    assert any("test_mod.py::test_t" in row for row in rows)


def test_list_live_runs_introspect(tmp_path) -> None:
    """`ditto list --live` delegates to the introspection pass."""
    manifest = [
        BackendManifest(
            location="redis://h/0",
            entries=[
                ManifestEntry(
                    "mod.test_live@k~0000000000000000.json", size_bytes=7, modified=None
                )
            ],
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
                    {
                        "nodeid": "test_x.py::test_remote",
                        "key": "k",
                        "recorder": "json",
                    }
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
                    {
                        "nodeid": "test_x.py::test_remote",
                        "key": "k",
                        "recorder": "json",
                    }
                ],
            }
        },
    }
    (tmp_path / "ditto.lock").write_text(json.dumps(lock))

    result = CliRunner().invoke(command, [str(tmp_path)])

    assert result.exit_code == 0
    assert "—" in result.output
    assert "0 B" not in result.output


@pytest.mark.parametrize("command", [cmd_list, cmd_status, cmd_stats])
def test_empty_inventory_explains_that_remote_snapshots_need_a_lock(
    command, tmp_path
) -> None:
    """An empty credential-free result directs remote-only users to live mode."""
    result = CliRunner().invoke(command, [str(tmp_path)])

    assert result.exit_code == 1
    assert "No snapshot files found" in result.output
    assert "no ditto.lock found" in result.output
    assert "use --live" in result.output


def test_list_hints_when_no_lockfile(tmp_path) -> None:
    """With local snapshots but no ditto.lock, list hints that remotes are hidden."""
    _make_local_snapshot(tmp_path)

    result = CliRunner().invoke(cmd_list, [str(tmp_path)])

    assert result.exit_code == 0
    assert "no ditto.lock found" in result.output


# ── _doctor_checks: backends ──────────────────────────────────────────────────


def test_returns_failing_check_with_error_detail_when_backend_load_raises(
    make_distribution,
) -> None:
    """A backend whose entry point fails to load gets a failing check with the
    error."""
    eps = make_distribution(
        "plug", "1.0", {"ditto_backends": {"broken": "ditto_no_such_module:x"}}
    )

    checks = _backend_checks(BackendRegistry(eps))

    (check,) = checks
    assert (check.name, check.ok) == ("backend: broken", False)
    assert "plug 1.0" in check.detail
    assert "ditto_no_such_module" in check.detail


def test_returns_one_passing_result_per_loadable_backend(make_distribution) -> None:
    """Each backend that loads produces exactly one passing check."""
    factory = "ditto.backends:FsspecMapping"
    eps = make_distribution(
        "plug", "1.0", {"ditto_backends": {"alpha": factory, "beta": factory}}
    )

    checks = _backend_checks(BackendRegistry(eps))

    actual = [(c.name, c.ok) for c in checks]
    expected = [("backend: alpha", True), ("backend: beta", True)]
    assert actual == expected


def test_reports_a_backend_contract_problem_once_instead_of_per_scheme(
    make_distribution,
) -> None:
    """A duplicated scheme fails one contract check, naming both distributions."""
    factory = "ditto.backends:FsspecMapping"
    first = make_distribution("plug-a", "1.0", {"ditto_backends": {"demo": factory}})
    second = make_distribution("plug-b", "2.0", {"ditto_backends": {"demo": factory}})

    checks = _backend_checks(BackendRegistry([*first, *second]))

    (check,) = checks
    assert (check.name, check.ok) == ("backend contract", False)
    assert "plug-a 1.0, plug-b 2.0" in check.detail
