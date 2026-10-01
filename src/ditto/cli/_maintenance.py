"""Commands that clean up snapshots and inspect the installed plugins."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .._theme import CREATED, MUTED, PATH, PRUNED, TEXT
from ..recorders._plugins import RecorderRegistry
from ._data import _load_recorder_infos
from ._diagnostics import _doctor_checks
from ._display import _render_doctor, _render_recorders

console = Console()


def _find_ditto_dirs(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob(".ditto") if p.is_dir())


@click.command(name="clean")
@click.argument(
    "path", default=".", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation prompt.")
def cmd_clean(path: Path, yes: bool):
    """Delete all .ditto/ directories under PATH.

    Shows a preview of what will be deleted and requires confirmation
    unless --yes is passed.

    \b
    Examples:
      ditto clean
      ditto clean --yes
      ditto clean tests/ci/ --yes
    """
    dirs = _find_ditto_dirs(path)
    if not dirs:
        console.print(f"[{MUTED}]No .ditto/ directories found.[/{MUTED}]")
        sys.exit(1)

    preview = Text()
    preview.append("Will delete:\n\n", style=f"bold {TEXT}")
    for d in dirs:
        preview.append(f"  {d}\n", style=PATH)

    console.print(Panel(preview, border_style=PRUNED, expand=False))

    if not yes:
        click.confirm(click.style("\nProceed?", fg="bright_white"), abort=True)

    for d in dirs:
        shutil.rmtree(d)
        t = Text()
        t.append("  deleted  ", style=f"bold {PRUNED}")
        t.append(str(d), style=PATH)
        console.print(t)

    n = len(dirs)
    console.print(
        f"\n[bold {CREATED}]Removed {n} "
        f".ditto/ director{'y' if n == 1 else 'ies'}.[/bold {CREATED}]"
    )


@click.command(name="recorders")
def cmd_recorders():
    """List all registered recorder plugins.

    \b
    Examples:
      ditto recorders
    """
    infos = _load_recorder_infos()
    if not infos:
        console.print(f"[{MUTED}]No recorders registered.[/{MUTED}]")
        sys.exit(1)
    _render_recorders(infos, console)
    problems = RecorderRegistry().problems
    if problems:
        console.print(
            f"[{PRUNED}]{len(problems)} plugin contract problem(s); run "
            f"`ditto doctor` for details.[/{PRUNED}]"
        )


@click.command(name="doctor")
def cmd_doctor():
    """Run health checks: plugin loading, pytest availability.

    \b
    Examples:
      ditto doctor
    """
    checks = _doctor_checks()
    _render_doctor(checks, console)
    if not all(c.ok for c in checks):
        sys.exit(1)
