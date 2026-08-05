"""Core package-boundary regressions for the 2.0 recorder change."""

import ast
import subprocess
import tomllib
from pathlib import Path

import pytest

import ditto


ROOT = Path(__file__).parents[2]
SOURCE = ROOT / "src" / "ditto"


def test_removed_public_api_is_absent() -> None:
    assert "pickle" not in ditto.__all__
    assert "DittoTestCase" not in ditto.__all__

    with pytest.raises(AttributeError):
        getattr(ditto, "pickle")
    with pytest.raises(AttributeError):
        getattr(ditto, "DittoTestCase")


def test_removed_modules_are_absent() -> None:
    assert not (SOURCE / "recorders" / "_pickle.py").exists()
    assert not (SOURCE / "_unittest.py").exists()


def test_core_source_does_not_import_pickle() -> None:
    offending: list[str] = []
    for source_file in SOURCE.rglob("*.py"):
        tree = ast.parse(source_file.read_text(), filename=str(source_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                alias.name == "pickle" for alias in node.names
            ):
                offending.append(str(source_file.relative_to(ROOT)))
            if isinstance(node, ast.ImportFrom) and node.module == "pickle":
                offending.append(str(source_file.relative_to(ROOT)))

    assert offending == []


def test_core_metadata_has_only_json_and_yaml_recorder_entry_points() -> None:
    with (ROOT / "pyproject.toml").open("rb") as file:
        project = tomllib.load(file)["project"]

    assert set(project["entry-points"]["ditto_recorders"]) == {"json", "yaml"}


def test_repository_tracks_no_pickle_snapshots() -> None:
    tracked_paths = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "*.pkl"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    tracked = [path for path in tracked_paths if (ROOT / path).exists()]

    assert tracked == []
