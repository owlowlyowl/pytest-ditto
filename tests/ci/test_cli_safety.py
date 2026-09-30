"""Command failure handling, cleanup boundaries, and pytest passthrough."""

import sys
from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from ditto.cli import cli
from ditto.cli import _maintenance, _pytest, _inventory
from ditto._inventory import InventoryError, build_inventory


def test_inventory_includes_the_selected_snapshot_directory(tmp_path):
    directory = tmp_path / ".ditto"
    directory.mkdir()
    (directory / "test_a@k~0123456789abcdef.json").write_text("1")
    manifest = build_inventory(directory, live=False)
    assert len(manifest) == 1
    assert len(manifest[0].entries) == 1


def test_clean_removes_nested_directories_only_once(tmp_path):
    directory = tmp_path / ".ditto"
    (directory / "nested" / ".ditto").mkdir(parents=True)
    result = CliRunner().invoke(cli, ["clean", str(tmp_path), "--yes"])
    assert result.exit_code == 0, result.output
    assert "Removed 1 .ditto/ directory" in result.output
    assert not directory.exists()


def test_clean_accepts_a_snapshot_directory_itself(tmp_path):
    directory = tmp_path / ".ditto"
    directory.mkdir()
    result = CliRunner().invoke(cli, ["clean", str(directory), "--yes"])
    assert result.exit_code == 0, result.output
    assert not directory.exists()


def test_clean_cancel_keeps_snapshots(tmp_path):
    directory = tmp_path / ".ditto"
    directory.mkdir()
    snapshot = directory / "keep.json"
    snapshot.write_text("1")
    result = CliRunner().invoke(cli, ["clean", str(tmp_path)], input="n\n")
    assert result.exit_code == 1
    assert snapshot.read_text() == "1"


def test_clean_does_not_follow_snapshot_directory_symlinks(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_text("safe")
    scope = tmp_path / "scope"
    scope.mkdir()
    (scope / ".ditto").symlink_to(outside, target_is_directory=True)
    result = CliRunner().invoke(cli, ["clean", str(scope), "--yes"])
    assert result.exit_code == 1
    assert (outside / "keep").read_text() == "safe"


def test_clean_reports_filesystem_errors(tmp_path, monkeypatch):
    (tmp_path / ".ditto").mkdir()
    monkeypatch.setattr(
        _maintenance.shutil, "rmtree", Mock(side_effect=PermissionError("denied"))
    )
    result = CliRunner().invoke(cli, ["clean", str(tmp_path), "--yes"])
    assert result.exit_code == 1
    assert "Could not remove" in result.stderr
    assert "denied" in result.stderr


@pytest.mark.parametrize(
    "command,flags",
    [
        ("run", []),
        ("update", ["--ditto-update"]),
        ("prune", ["--ditto-prune"]),
        ("lock", ["--ditto-lock"]),
        ("verify", ["--ditto-verify"]),
    ],
)
def test_pytest_arguments_and_exit_status_are_preserved(command, flags, monkeypatch):
    run = Mock(return_value=Mock(returncode=5))
    monkeypatch.setattr(_pytest.subprocess, "run", run)
    args = ["tests/test_api.py::test_a[x y]", "-k", "a or b", "--maxfail=1"]
    result = CliRunner().invoke(cli, [command, *args])
    assert result.exit_code == 5
    run.assert_called_once_with(
        [sys.executable, "-m", "pytest", *flags, *args], check=False
    )


def test_inventory_error_is_literal_and_goes_to_stderr(tmp_path, monkeypatch):
    monkeypatch.setattr(
        _inventory,
        "build_inventory",
        Mock(side_effect=InventoryError("bad [/][red] path")),
    )
    result = CliRunner().invoke(cli, ["list", str(tmp_path)])
    assert result.exit_code == 1
    assert "bad [/][red] path" in result.stderr
    assert result.stdout == ""


def test_lint_empty_inventory_does_not_claim_validation(tmp_path):
    result = CliRunner().invoke(cli, ["lint", str(tmp_path)])
    assert result.exit_code == 0
    assert "No snapshot files found" in result.output
    assert "All snapshots are valid" not in result.output
