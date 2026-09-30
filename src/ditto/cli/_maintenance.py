"""Local snapshot cleanup and plugin diagnostic commands."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ditto._theme import MUTED, TEXT, PATH, PRUNED, CREATED
from ditto.recorders._plugins import RecorderRegistry
from ._data import _load_recorder_infos
from ._diagnostics import _doctor_checks
from ._display import _render_recorders, _render_doctor

console = Console()


def _find_ditto_dirs(root: Path) -> list[Path]:
    # Deleting a parent also removes nested .ditto directories. Never schedule
    # those twice or follow a directory symlink outside the selected tree.
    root = root.absolute()
    candidates = sorted(
        p
        for p in (root, *root.rglob(".ditto"))
        if p.name == ".ditto" and p.is_dir() and not p.is_symlink()
    )
    selected: list[Path] = []
    for candidate in candidates:
        if not any(parent in candidate.parents for parent in selected):
            selected.append(candidate)
    return selected


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
    if path.is_symlink():
        raise click.ClickException("Clean PATH must not be a directory symlink.")
    try:
        dirs = _find_ditto_dirs(path)
    except OSError as exc:
        raise click.ClickException(
            f"Could not find snapshot directories: {exc}"
        ) from exc
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
        try:
            shutil.rmtree(d)
        except OSError as exc:
            raise click.ClickException(f"Could not remove {d}: {exc}") from exc
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
