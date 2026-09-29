"""Verify release artifacts without importing the repository source tree.

The dist directory holds one directory per package, named after its distribution
(see build_release_artifacts.py): core's checks run on ``pytest-ditto/`` and the
plugin checks on every other package.
"""

from __future__ import annotations

import argparse
import ast
import configparser
import os
import subprocess
import sys
import tempfile
import zipfile
from email import message_from_bytes
from email.message import Message
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from build_release_artifacts import packages


ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_PLUGIN = ROOT / "tests" / "release" / "synthetic_plugin"
CORE = "pytest-ditto"
# The plugin contract's major version: every plugin requires pytest-ditto below it.
CONTRACT_CEILING = "<3"
EXPECTED_JSON = (
    b'{\n  "nested": [\n    1,\n    true,\n    null\n  ],\n  "unicode": "\xce\xbb"\n}\n'
)


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    display = " ".join(command)
    print(f"+ {display}", flush=True)
    environment = os.environ.copy()
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONPATH", None)
    subprocess.run(command, cwd=cwd, env=environment, check=True)


def _one_artifact(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if len(matches) != 1:
        names = ", ".join(path.name for path in matches) or "none"
        raise RuntimeError(
            f"Expected exactly one {pattern!r} artifact in {directory}, found {names}."
        )
    return matches[0].resolve()


def _assert_no_pickle_import(path: str, source: str) -> None:
    tree = ast.parse(source, filename=path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name == "pickle" for alias in node.names
        ):
            raise RuntimeError(f"Core wheel imports pickle in {path}.")
        if isinstance(node, ast.ImportFrom) and node.module == "pickle":
            raise RuntimeError(f"Core wheel imports pickle in {path}.")


def _verify_wheel_boundary(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        members = set(archive.namelist())
        forbidden = {"ditto/_unittest.py", "ditto/recorders/_pickle.py"}
        present = sorted(forbidden & members)
        if present:
            raise RuntimeError(f"Forbidden core wheel members: {', '.join(present)}")

        entry_point_members = sorted(
            name for name in members if name.endswith(".dist-info/entry_points.txt")
        )
        if len(entry_point_members) != 1:
            raise RuntimeError(
                f"Expected exactly one dist-info/entry_points.txt in {wheel.name}."
            )

        entry_points = configparser.ConfigParser()
        entry_points.optionxform = str
        entry_points.read_string(archive.read(entry_point_members[0]).decode("utf-8"))
        recorder_names = set(entry_points.options("ditto_recorders"))
        if recorder_names != {"json", "yaml"}:
            raise RuntimeError(
                f"Unexpected built-in recorder entry points: {sorted(recorder_names)}"
            )
        if entry_points.has_section("ditto_marks"):
            raise RuntimeError("Core wheel registers the removed ditto_marks group.")

        for name in sorted(members):
            if name.startswith("ditto/") and name.endswith(".py"):
                source = archive.read(name).decode("utf-8")
                _assert_no_pickle_import(name, source)


def _venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _verify_installed_wheel(wheel: Path, work: Path) -> None:
    venv = work / "venv"
    _run(["uv", "venv", "--python", sys.executable, str(venv)], cwd=work)
    python = _venv_python(venv)
    _run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            str(wheel),
            str(SYNTHETIC_PLUGIN),
        ],
        cwd=work,
    )

    probe = """
import importlib.metadata
import importlib.util

import pytest

import ditto
from ditto import recorders

assert importlib.util.find_spec("ditto._unittest") is None
assert importlib.util.find_spec("ditto.recorders._pickle") is None
assert "DittoTestCase" not in ditto.__all__
assert "pickle" not in ditto.__all__
assert not hasattr(ditto, "DittoTestCase")
assert not hasattr(ditto, "pickle")

try:
    from ditto import DittoTestCase
except ImportError:
    pass
else:
    raise AssertionError("DittoTestCase remains importable from the built wheel.")

try:
    from ditto import pickle
except ImportError:
    pass
else:
    raise AssertionError("pickle remains importable from the built wheel.")

distribution = importlib.metadata.distribution("pytest-ditto")
core_recorders = {
    entry.name for entry in distribution.entry_points
    if entry.group == "ditto_recorders"
}
assert core_recorders == {"json", "yaml"}
assert recorders.RECORDER_REGISTRY.problems == ()
assert recorders.get("json") is recorders.default()
assert isinstance(recorders.get("synthetic"), recorders.Recorder)
assert isinstance(recorders.get("verify.dotted"), recorders.Recorder)
assert ditto.synthetic == pytest.mark.record("synthetic")
assert ditto.verify.dotted == pytest.mark.record("verify.dotted")
"""
    _run([str(python), "-I", "-c", probe], cwd=work)

    smoke = work / "smoke"
    smoke.mkdir()
    test_file = smoke / "test_installed.py"
    test_file.write_text(
        """\
import ditto


def test_no_mark_json_round_trip(snapshot):
    value = {"unicode": "\u03bb", "nested": [1, True, None]}
    assert snapshot.recorder_name == "json"
    assert snapshot(value, key="value") == value


@ditto.synthetic
def test_external_recorder_and_dynamic_mark(snapshot):
    value = {"external": True}
    assert snapshot.recorder_name == "synthetic"
    assert snapshot(value, key="value") == value


@ditto.verify.dotted
def test_external_recorder_and_namespaced_mark(snapshot):
    value = {"namespaced": True}
    assert snapshot.recorder_name == "verify.dotted"
    assert snapshot(value, key="value") == value
""",
        encoding="utf-8",
    )

    pytest_command = [str(python), "-m", "pytest", "-q", str(test_file)]
    _run(pytest_command, cwd=smoke)

    json_snapshots = list((smoke / ".ditto").glob("*@value~*.json"))
    if len(json_snapshots) != 1:
        raise RuntimeError(
            "Installed-wheel smoke test did not create one JSON snapshot."
        )
    if json_snapshots[0].read_bytes() != EXPECTED_JSON:
        raise RuntimeError(
            "Installed wheel did not write the expected golden JSON bytes."
        )
    if len(list((smoke / ".ditto").glob("*@value~*.synthetic"))) != 1:
        raise RuntimeError("Synthetic external recorder did not persist its snapshot.")
    if len(list((smoke / ".ditto").glob("*@value~*.verify.dotted"))) != 1:
        raise RuntimeError("Namespaced external recorder did not persist its snapshot.")

    _run(pytest_command, cwd=smoke)


def _wheel_metadata(wheel: Path) -> Message:
    with zipfile.ZipFile(wheel) as archive:
        names = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(names) != 1:
            raise RuntimeError(
                f"Expected exactly one dist-info/METADATA in {wheel.name}."
            )
        return message_from_bytes(archive.read(names[0]))


def _wheel_entry_points(wheel: Path) -> configparser.ConfigParser:
    entry_points = configparser.ConfigParser()
    entry_points.optionxform = str
    with zipfile.ZipFile(wheel) as archive:
        names = [
            name
            for name in archive.namelist()
            if name.endswith(".dist-info/entry_points.txt")
        ]
        if len(names) == 1:
            entry_points.read_string(archive.read(names[0]).decode("utf-8"))
    return entry_points


def _rebuild_wheel(sdist: Path, direct_wheel: Path, work: Path) -> Path:
    """Build a wheel from `sdist` and check it matches the one built from source."""
    rebuilt_dist = work / "rebuilt"
    rebuilt_dist.mkdir()
    _run(
        ["uv", "build", "--wheel", "--out-dir", str(rebuilt_dist), str(sdist)],
        cwd=work,
    )
    rebuilt_wheel = _one_artifact(rebuilt_dist, "*.whl")
    if rebuilt_wheel.name != direct_wheel.name:
        raise RuntimeError(
            "Wheel rebuilt from sdist has a different name: "
            f"{rebuilt_wheel.name} != {direct_wheel.name}."
        )
    rebuilt = _wheel_metadata(rebuilt_wheel).get_all("Requires-Dist") or []
    direct = _wheel_metadata(direct_wheel).get_all("Requires-Dist") or []
    if sorted(rebuilt) != sorted(direct):
        raise RuntimeError(
            f"Wheel rebuilt from sdist has different requirements: {rebuilt} != "
            f"{direct}."
        )
    return rebuilt_wheel


def verify_core(directory: Path, work: Path) -> None:
    direct_wheel = _one_artifact(directory, "*.whl")
    sdist = _one_artifact(directory, "*.tar.gz")
    _verify_wheel_boundary(direct_wheel)
    _verify_wheel_boundary(_rebuild_wheel(sdist, direct_wheel, work))
    _verify_installed_wheel(direct_wheel, work)


def _verify_core_floor(metadata: Message) -> None:
    """Check the plugin requires pytest-ditto>=<its own public version>,<3.

    plugins/<name>/hatch_build.py generates the requirement at build time.
    """
    public_version = Version(metadata["Version"]).public
    expected = SpecifierSet(f">={public_version},{CONTRACT_CEILING}")
    core_requirements = [
        requirement
        for line in metadata.get_all("Requires-Dist") or []
        if (requirement := Requirement(line)).name == CORE
    ]
    if len(core_requirements) != 1:
        raise RuntimeError(
            f"{metadata['Name']} must require {CORE} exactly once, found "
            f"{[str(requirement) for requirement in core_requirements]}."
        )
    (requirement,) = core_requirements
    if (
        requirement.specifier != expected
        or requirement.marker is not None
        or requirement.extras
    ):
        raise RuntimeError(
            f"{metadata['Name']} requires {requirement}, expected {CORE}{expected}."
        )


def _verify_plugin_wheel(wheel: Path) -> dict[str, str]:
    """Check the plugin wheel's metadata; return its recorder entry points."""
    _verify_core_floor(_wheel_metadata(wheel))
    entry_points = _wheel_entry_points(wheel)
    if entry_points.has_section("ditto_marks"):
        raise RuntimeError(f"{wheel.name} registers the removed ditto_marks group.")
    if not entry_points.has_section("ditto_recorders") or not entry_points.options(
        "ditto_recorders"
    ):
        raise RuntimeError(f"{wheel.name} registers no ditto_recorders entry points.")
    return dict(entry_points.items("ditto_recorders"))


def _venv_script(venv: Path, name: str) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / f"{name}.exe"
    return venv / "bin" / name


def _verify_installed_plugin(
    core_wheel: Path, plugin_wheel: Path, recorders: dict[str, str], work: Path
) -> None:
    """Install core and the plugin in a clean venv; load its recorders and marks."""
    venv = work / "venv"
    _run(["uv", "venv", "--python", sys.executable, str(venv)], cwd=work)
    python = _venv_python(venv)
    _run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            str(core_wheel),
            str(plugin_wheel),
        ],
        cwd=work,
    )

    modules = sorted({
        target.split(":")[0].split(".")[0] for target in recorders.values()
    })
    probe = """
import sys

import pytest

import ditto
from ditto import recorders

names, modules = sys.argv[1].split(","), sys.argv[2].split(",")

# Contract rule 5: importing ditto doesn't import plugin modules.
imported = [module for module in modules if module in sys.modules]
assert not imported, f"import ditto imported {imported}"

assert recorders.RECORDER_REGISTRY.problems == ()
for name in names:
    assert isinstance(recorders.get(name), recorders.Recorder), name
    mark = ditto
    for part in name.split("."):
        mark = getattr(mark, part)
    assert mark == pytest.mark.record(name), name
"""
    _run(
        [
            str(python),
            "-I",
            "-c",
            probe,
            ",".join(sorted(recorders)),
            ",".join(modules),
        ],
        cwd=work,
    )
    _run([str(_venv_script(venv, "ditto")), "doctor"], cwd=work)


def verify_plugin(directory: Path, core_wheel: Path, work: Path) -> None:
    direct_wheel = _one_artifact(directory, "*.whl")
    sdist = _one_artifact(directory, "*.tar.gz")
    recorders = _verify_plugin_wheel(direct_wheel)
    _verify_plugin_wheel(_rebuild_wheel(sdist, direct_wheel, work))
    _verify_installed_plugin(core_wheel, direct_wheel, recorders, work)


def _verify_layout(dist: Path, expected_version: str | None) -> dict[str, Path]:
    """Check `dist` holds exactly this repo's packages, all at one version."""
    expected = set(packages())
    found = {path.name for path in dist.iterdir() if path.is_dir()}
    if found != expected:
        raise RuntimeError(
            f"Expected package directories {sorted(expected)} in {dist}, found "
            f"{sorted(found)}."
        )

    wheels = {name: _one_artifact(dist / name, "*.whl") for name in sorted(expected)}
    versions = {
        name: Version(_wheel_metadata(wheel)["Version"])
        for name, wheel in wheels.items()
    }
    for name, wheel in wheels.items():
        distribution = _wheel_metadata(wheel)["Name"]
        if distribution != name:
            raise RuntimeError(f"{dist / name} holds {distribution}, not {name}.")
    if len(set(versions.values())) != 1:
        raise RuntimeError(f"Packages are not at one version: {versions}.")
    version = versions[CORE]
    if expected_version is not None and version != Version(expected_version):
        raise RuntimeError(f"Packages are at {version}, expected {expected_version}.")
    return wheels


def verify(dist: Path, expected_version: str | None = None) -> None:
    wheels = _verify_layout(dist, expected_version)
    for name in wheels:
        with tempfile.TemporaryDirectory(prefix=f"{name}-artifacts-") as temporary:
            work = Path(temporary)
            if name == CORE:
                verify_core(dist / name, work)
            else:
                verify_plugin(dist / name, wheels[CORE], work)
        print(f"Verified {name} artifacts in {dist / name}.", flush=True)

    print(f"Verified release artifacts in {dist}.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "dist",
        type=Path,
        help="Directory containing one directory of artifacts per package.",
    )
    parser.add_argument(
        "--version",
        help="Fail unless every package is at this version, e.g. the release tag.",
    )
    arguments = parser.parse_args()
    verify(arguments.dist.resolve(), arguments.version)


if __name__ == "__main__":
    main()
