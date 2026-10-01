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
from ._display import _render_doctor, _render_recorders, pass_console


def _find_ditto_dirs(root: Path) -> tuple[list[Path], list[Path]]:
    """Return (directories to delete, symlink `.ditto` entries skipped).

    PATH itself is included when it is a `.ditto` directory. Nested `.ditto`
    directories are dropped because deleting the parent removes them. Symlinks
    are never followed or scheduled for `rmtree`.
    """
    root = root.absolute()
    skipped: list[Path] = []
    candidates: list[Path] = []
    for path in (root, *root.rglob(".ditto")):
        if path.name != ".ditto":
            continue
        if path.is_symlink():
            skipped.append(path)
            continue
        if path.is_dir():
            candidates.append(path)
    selected: list[Path] = []
    for candidate in sorted(candidates):
        if not any(parent in candidate.parents for parent in selected):
            selected.append(candidate)
    return selected, skipped


@click.command(name="clean")
@click.argument(
    "path", default=".", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation prompt.")
@pass_console
def cmd_clean(console: Console, path: Path, yes: bool):
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
        dirs, skipped = _find_ditto_dirs(path)
    except OSError as exc:
        raise click.ClickException(
            f"Could not find snapshot directories: {exc}"
        ) from exc

    for link in skipped:
        console.print(
            Text.assemble(
                ("  skipped  ", f"bold {MUTED}"),
                (str(link), PATH),
                " (symlink)",
            )
        )

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

    removed: list[Path] = []
    failed: list[tuple[Path, OSError]] = []
    for d in dirs:
        try:
            shutil.rmtree(d)
        except OSError as exc:
            failed.append((d, exc))
            t = Text()
            t.append("  failed   ", style=f"bold {PRUNED}")
            t.append(str(d), style=PATH)
            t.append(f": {exc}", style=MUTED)
            console.print(t)
        else:
            removed.append(d)
            t = Text()
            t.append("  deleted  ", style=f"bold {PRUNED}")
            t.append(str(d), style=PATH)
            console.print(t)

    n = len(removed)
    console.print(
        f"\n[bold {CREATED}]Removed {n} "
        f".ditto/ director{'y' if n == 1 else 'ies'}.[/bold {CREATED}]"
    )
    if failed:
        names = ", ".join(str(path) for path, _ in failed)
        console.print(
            Text(
                f"Could not remove {len(failed)} "
                f".ditto/ director{'y' if len(failed) == 1 else 'ies'}: {names}",
                style=PRUNED,
            )
        )
        sys.exit(1)


@click.command(name="recorders")
@pass_console
def cmd_recorders(console: Console):
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
@pass_console
def cmd_doctor(console: Console):
    """Run health checks: plugin loading, pytest availability.

    \b
    Examples:
      ditto doctor
    """
    checks = _doctor_checks()
    _render_doctor(checks, console)
    if not all(c.ok for c in checks):
        sys.exit(1)
