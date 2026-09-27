"""Build the sdist and wheel of core and every plugin under plugins/.

Each package gets its own directory, named after its distribution:
``dist/pytest-ditto/``, ``dist/pytest-ditto-pandas/`` and so on. The output
directory is emptied first, so it only ever holds one release's artifacts.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def packages() -> dict[str, Path]:
    """Return every package's distribution name and source directory, core first."""
    plugins = sorted(path.parent for path in ROOT.glob("plugins/*/pyproject.toml"))
    found = {}
    for project in [ROOT, *plugins]:
        with (project / "pyproject.toml").open("rb") as file:
            found[tomllib.load(file)["project"]["name"]] = project
    return found


def build(dist: Path) -> None:
    if dist.exists():
        shutil.rmtree(dist)
    for name, source in packages().items():
        command = [
            "uv",
            "build",
            "--sdist",
            "--wheel",
            "--out-dir",
            str(dist / name),
            str(source),
        ]
        print(f"+ {' '.join(command)}", flush=True)
        subprocess.run(command, check=True)
        # uv adds a .gitignore to each output directory; only distributions belong
        # in what gets published.
        (dist / name / ".gitignore").unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dist", type=Path, help="Output directory, emptied first.")
    build(parser.parse_args().dist.resolve())


if __name__ == "__main__":
    main()
