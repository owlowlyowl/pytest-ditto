"""Cleanup boundaries and inventory of a `.ditto` path itself."""

from pathlib import Path

from click.testing import CliRunner

from ditto._inventory import build_inventory
from ditto.cli import _maintenance, cli


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
    assert "symlink" in result.output
    assert (outside / "keep").read_text() == "safe"


def test_clean_reports_filesystem_errors_and_continues(tmp_path, monkeypatch):
    first = tmp_path / "a" / ".ditto"
    second = tmp_path / "b" / ".ditto"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    original = _maintenance.shutil.rmtree

    def rmtree(path, *args, **kwargs):
        if Path(path) == first:
            raise PermissionError("denied")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(_maintenance.shutil, "rmtree", rmtree)
    result = CliRunner().invoke(cli, ["clean", str(tmp_path), "--yes"])
    assert result.exit_code == 1
    assert "Could not remove" in result.output
    assert "denied" in result.output
    assert first.exists()
    assert not second.exists()


def test_clean_refuses_a_symlinked_path(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    result = CliRunner().invoke(cli, ["clean", str(link), "--yes"])
    assert result.exit_code != 0
    assert "symlink" in result.output.lower()
