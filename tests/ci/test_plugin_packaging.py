"""Packaging rules shared by the first-party plugins under plugins/."""

import tomllib
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[2]
PLUGINS = sorted(path.parent for path in (ROOT / "plugins").glob("*/pyproject.toml"))


def _pyproject(plugin: Path) -> dict:
    with (plugin / "pyproject.toml").open("rb") as file:
        return tomllib.load(file)


def test_every_plugin_carries_the_same_core_floor_hook() -> None:
    hooks = {plugin.name: (plugin / "hatch_build.py").read_text() for plugin in PLUGINS}

    assert set(hooks) == {"pandas", "pickle", "polars", "pyarrow"}
    assert len(set(hooks.values())) == 1


@pytest.mark.parametrize("plugin", PLUGINS, ids=lambda plugin: plugin.name)
def test_plugin_dependencies_come_from_the_core_floor_hook(plugin: Path) -> None:
    pyproject = _pyproject(plugin)
    project = pyproject["project"]
    hatch = pyproject["tool"]["hatch"]

    assert "dependencies" in project["dynamic"]
    assert "dependencies" not in project
    assert "custom" in hatch["metadata"]["hooks"]
    assert "hatch_build.py" in hatch["build"]["targets"]["sdist"]["only-include"]


@pytest.mark.parametrize("plugin", PLUGINS, ids=lambda plugin: plugin.name)
def test_plugin_leaves_the_core_requirement_to_the_hook(plugin: Path) -> None:
    hook = _pyproject(plugin)["tool"]["hatch"]["metadata"]["hooks"]["custom"]

    assert not any(
        requirement.startswith("pytest-ditto") for requirement in hook["dependencies"]
    )
