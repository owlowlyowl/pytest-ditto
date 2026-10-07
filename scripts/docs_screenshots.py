"""Regenerate the CLI screenshots in docs/src/img from real command output.

Builds a small demo project in a temporary directory, runs the installed
`ditto` commands against it with colour forced on, and writes each command's
terminal output as an SVG. Run it from an environment where pytest-ditto is
installed, after a change to what a command prints:

    pixi run -e py312 python scripts/docs_screenshots.py

`ditto recorders` lists the recorder plugins installed in that environment, and
`ditto list` and `ditto status` show today's date, so a rerun changes those.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from rich.console import Console
from rich.text import Text


ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "docs" / "src" / "img"
WIDTH = 100

TESTS = """\
import pytest


def test_refund(snapshot):
    assert snapshot({"status": "refunded", "amount": 12.5}, key="response") == {
        "status": "refunded",
        "amount": 12.5,
    }


@pytest.mark.parametrize("region", ["eu", "us"])
def test_totals(snapshot, region):
    subtotal = 100
    assert snapshot(subtotal, key="subtotal") == subtotal
    assert snapshot(subtotal // 10, key="tax") == subtotal // 10
"""

CONFIG = """\
import ditto


@ditto.yaml
def test_config(snapshot):
    config = {"retries": 3, "timeout": 30}
    assert snapshot(config, key="defaults") == config
"""


def _environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("NO_COLOR", None)
    environment.update(
        FORCE_COLOR="1", TERM="xterm-256color", COLUMNS=str(WIDTH), LINES="50"
    )
    return environment


def _run(command: list[str], project: Path) -> str:
    """Run `command` in `project`; return its stdout and stderr as one stream."""
    result = subprocess.run(
        command,
        cwd=project,
        env=_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    return result.stdout


def _ditto(*args: str) -> list[str]:
    return [sys.executable, "-c", "from ditto.cli import cli; cli()", *args]


def _save(name: str, title: str, output: str) -> None:
    """Write `output`, as a terminal would show it, to docs/src/img/<name>.svg."""
    console = Console(record=True, width=WIDTH, force_terminal=True, file=io.StringIO())
    console.print(Text.from_ansi(output.strip("\n")))
    (IMAGES / f"{name}.svg").write_text(console.export_svg(title=title))
    print(f"wrote {IMAGES / f'{name}.svg'}")


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        project = Path(directory)
        tests = project / "tests"
        tests.mkdir()
        (project / "conftest.py").write_text("")
        (tests / "test_orders.py").write_text(TESTS)
        (tests / "test_config.py").write_text(CONFIG)
        _run([sys.executable, "-m", "pytest", "-q"], project)

        _save("ditto-list", "ditto list", _run(_ditto("list"), project))
        _save("ditto-status", "ditto status", _run(_ditto("status"), project))
        _save("ditto-recorders", "ditto recorders", _run(_ditto("recorders"), project))

        (tests / "test_orders.py").write_text(
            TESTS.replace("subtotal = 100", "subtotal = 120")
        )
        _save("ditto-update", "ditto update", _run(_ditto("update", "-q"), project))
        _save(
            "ditto-clean", "ditto clean --yes", _run(_ditto("clean", "--yes"), project)
        )


if __name__ == "__main__":
    main()
