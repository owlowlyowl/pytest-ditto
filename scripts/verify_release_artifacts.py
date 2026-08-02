"""Verify release artifacts without importing the repository source tree."""

from __future__ import annotations

import argparse
import ast
import configparser
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_PLUGIN = ROOT / "tests" / "release" / "synthetic_plugin"
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
        if entry_points.has_option("ditto_marks", "pickle"):
            raise RuntimeError("Core wheel exposes a static pickle mark entry point.")

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
assert recorders.default().extension == "json"
assert recorders.get("synthetic").extension == "synthetic"
assert ditto.synthetic is not None
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
    assert snapshot.recorder.extension == "json"
    assert snapshot(value, key="value") == value


@ditto.synthetic
def test_external_recorder_and_dynamic_mark(snapshot):
    value = {"external": True}
    assert snapshot.recorder.extension == "synthetic"
    assert snapshot(value, key="value") == value
""",
        encoding="utf-8",
    )

    pytest_command = [str(python), "-m", "pytest", "-q", str(test_file)]
    _run(pytest_command, cwd=smoke)

    json_snapshots = list((smoke / ".ditto").glob("*@value.json"))
    if len(json_snapshots) != 1:
        raise RuntimeError(
            "Installed-wheel smoke test did not create one JSON snapshot."
        )
    if json_snapshots[0].read_bytes() != EXPECTED_JSON:
        raise RuntimeError(
            "Installed wheel did not write the expected golden JSON bytes."
        )
    if len(list((smoke / ".ditto").glob("*@value.synthetic"))) != 1:
        raise RuntimeError("Synthetic external recorder did not persist its snapshot.")

    _run(pytest_command, cwd=smoke)


def verify(dist: Path) -> None:
    direct_wheel = _one_artifact(dist, "*.whl")
    sdist = _one_artifact(dist, "*.tar.gz")
    _verify_wheel_boundary(direct_wheel)

    with tempfile.TemporaryDirectory(prefix="pytest-ditto-artifacts-") as temporary:
        work = Path(temporary)
        rebuilt_dist = work / "rebuilt"
        rebuilt_dist.mkdir()
        _run(
            [
                "uv",
                "build",
                "--wheel",
                "--out-dir",
                str(rebuilt_dist),
                str(sdist),
            ],
            cwd=work,
        )
        rebuilt_wheel = _one_artifact(rebuilt_dist, "*.whl")
        if rebuilt_wheel.name != direct_wheel.name:
            raise RuntimeError(
                "Wheel rebuilt from sdist has a different name: "
                f"{rebuilt_wheel.name} != {direct_wheel.name}."
            )
        _verify_wheel_boundary(rebuilt_wheel)
        _verify_installed_wheel(direct_wheel, work)

    print(f"Verified release artifacts in {dist}.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "dist",
        type=Path,
        help="Directory containing exactly one pytest-ditto sdist and wheel.",
    )
    arguments = parser.parse_args()
    verify(arguments.dist.resolve())


if __name__ == "__main__":
    main()
