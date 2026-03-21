"""
ditto CLI — snapshot management for pytest-ditto.

Subcommands
-----------
run         Run pytest, reporting any snapshot activity at the end.
update      Re-run pytest with --ditto-update to regenerate snapshots.
prune       Re-run pytest with --ditto-prune to remove stale snapshots.
list        List all snapshot files under a path.
clean       Delete all .ditto/ directories under a path.
status      Show aggregate statistics for snapshots under a path.
recorders   List all registered recorder plugins.
"""

from __future__ import annotations

import importlib.metadata
import shutil
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ditto._theme import (
    CREATED, UPDATED, UNUSED, PRUNED,
    TITLE, HEADER, MUTED, ACCENT, PATH,
    TEXT, SUBTEXT1,
    TEAL, SKY, MAUVE, FLAMINGO,
)


console = Console()

_RECORDER_PALETTE = (
    ACCENT,    # peach
    UPDATED,   # blue
    CREATED,   # green
    UNUSED,    # yellow
    TEAL,
    SKY,
    MAUVE,
    FLAMINGO,
)


def _build_colour_map(recorder_names: Iterable[str]) -> dict[str, str]:
    """Map recorder names to palette colours, assigned by sorted order — deterministic and pure."""
    return {
        name: _RECORDER_PALETTE[i % len(_RECORDER_PALETTE)]
        for i, name in enumerate(sorted(recorder_names))
    }


def _find_ditto_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob(".ditto/*") if p.is_file())


def _find_ditto_dirs(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob(".ditto") if p.is_dir())


def _ext_to_recorder() -> dict[str, tuple[str, str]]:
    """Return mapping of extension → (recorder_name, dist_name)."""
    result: dict[str, tuple[str, str]] = {}
    for ep in importlib.metadata.entry_points(group="ditto_recorders"):
        try:
            recorder = ep.load()
            ext = f".{recorder.extension}"
            dist = ep.dist.name if ep.dist else "unknown"
            result[ext] = (ep.name, dist)
        except Exception:
            pass
    return result


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} TB"


# ── Status aggregation ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SnapshotStats:
    total_count: int
    total_size: int
    by_recorder: dict[str, tuple[int, int]]  # name → (count, bytes)
    oldest: tuple[float, Path] | None
    newest: tuple[float, Path] | None


def gather_stats(files: list[Path], ext_map: dict[str, tuple[str, str]]) -> SnapshotStats:
    """Aggregate snapshot file statistics. Pure — no I/O beyond the stat() calls on already-found files."""
    total_size = 0
    by_recorder: dict[str, tuple[int, int]] = {}
    oldest: tuple[float, Path] | None = None
    newest: tuple[float, Path] | None = None

    for fp in files:
        stat = fp.stat()
        sz = stat.st_size
        mtime = stat.st_mtime
        total_size += sz

        ext = fp.suffix
        recorder_name = ext_map.get(ext, (ext.lstrip("."), ""))[0] if ext else ""
        count, total = by_recorder.get(recorder_name, (0, 0))
        by_recorder[recorder_name] = (count + 1, total + sz)

        if oldest is None or mtime < oldest[0]:
            oldest = (mtime, fp)
        if newest is None or mtime > newest[0]:
            newest = (mtime, fp)

    return SnapshotStats(
        total_count=len(files),
        total_size=total_size,
        by_recorder=by_recorder,
        oldest=oldest,
        newest=newest,
    )


def render_stats(stats: SnapshotStats, console: Console) -> None:
    """Render a SnapshotStats value as a Rich panel."""
    colour_map = _build_colour_map(stats.by_recorder.keys())

    lines = Text()
    lines.append("  Total snapshots  ", style=MUTED)
    lines.append(f"{stats.total_count}\n", style=f"bold {TEXT}")
    lines.append("  Total size       ", style=MUTED)
    lines.append(f"{_human_size(stats.total_size)}\n", style=f"bold {TEXT}")
    lines.append("\n")
    lines.append("  By recorder:\n", style=f"bold {HEADER}")
    count_w = max(len(str(c)) for c, _ in stats.by_recorder.values())
    size_w = max(len(_human_size(s)) for _, s in stats.by_recorder.values())
    for name, (count, sz) in sorted(stats.by_recorder.items()):
        lines.append(f"    {name:<12}", style=colour_map.get(name, MUTED))
        lines.append(f"  {count:>{count_w}}  ", style=TEXT)
        lines.append(f"{_human_size(sz):>{size_w}}\n", style=MUTED)

    if stats.oldest and stats.newest:
        lines.append("\n")
        oldest_date = datetime.fromtimestamp(stats.oldest[0]).strftime("%Y-%m-%d")
        newest_date = datetime.fromtimestamp(stats.newest[0]).strftime("%Y-%m-%d")
        lines.append("  Oldest  ", style=MUTED)
        lines.append(f"{stats.oldest[1].name}  ", style=PATH)
        lines.append(f"{oldest_date}\n", style=MUTED)
        lines.append("  Newest  ", style=MUTED)
        lines.append(f"{stats.newest[1].name}  ", style=PATH)
        lines.append(f"{newest_date}", style=MUTED)

    console.print(Panel(
        lines,
        title=f"[bold {TITLE}]ditto status[/bold {TITLE}]",
        border_style=TITLE,
        expand=False,
    ))


# ── CLI commands ──────────────────────────────────────────────────────────────

@click.group()
def cli():
    """pytest-ditto snapshot management."""


@cli.command(name="run", context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def cmd_run(pytest_args):
    """Run pytest, reporting any snapshot activity at the end.

    Any extra arguments are passed directly to pytest.

    \b
    Examples:
      ditto run
      ditto run tests/ci/
      ditto run tests/ci/ -k test_foo
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *pytest_args],
        check=False,
    )
    sys.exit(result.returncode)


@cli.command(name="update", context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def cmd_update(pytest_args):
    """Re-run pytest with --ditto-update to regenerate snapshots.

    Any extra arguments are passed directly to pytest.

    \b
    Examples:
      ditto update
      ditto update tests/ci/
      ditto update tests/ci/ -k test_foo
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--ditto-update", *pytest_args],
        check=False,
    )
    sys.exit(result.returncode)


@cli.command(name="prune", context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def cmd_prune(pytest_args):
    """Re-run pytest with --ditto-prune to remove stale snapshots.

    Any extra arguments are passed directly to pytest.

    \b
    Warning: using -k for a partial run may falsely classify snapshots for
    un-run tests as unused.

    \b
    Examples:
      ditto prune
      ditto prune tests/ci/
    """
    if any(arg in ("-k", "--keyword") or arg.startswith("-k") for arg in pytest_args):
        console.print(
            f"[bold {ACCENT}]Warning:[/bold {ACCENT}] "
            f"[{SUBTEXT1}]using -k with 'ditto prune' runs only a subset of tests. "
            f"Snapshots for skipped tests will be treated as unused and deleted.[/{SUBTEXT1}]",
            highlight=False,
        )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--ditto-prune", *pytest_args],
        check=False,
    )
    sys.exit(result.returncode)


@cli.command(name="list")
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False, path_type=Path))
def cmd_list(path: Path):
    """List all snapshot files under PATH (default: current directory).

    \b
    Examples:
      ditto list
      ditto list tests/ci/
    """
    files = _find_ditto_files(path)
    if not files:
        console.print(f"[{MUTED}]No snapshot files found.[/{MUTED}]")
        return

    ext_map = _ext_to_recorder()
    colour_map = _build_colour_map(v[0] for v in ext_map.values())

    table = Table(
        title=f"[bold {TITLE}]ditto snapshots[/bold {TITLE}]",
        border_style=MUTED,
        header_style=f"bold {HEADER}",
        show_header=True,
    )
    table.add_column("Test", style=TEXT)
    table.add_column("Key", style=SUBTEXT1)
    table.add_column("Recorder")
    table.add_column("Size", justify="right", style=MUTED)
    table.add_column("Modified", style=MUTED)

    for fp in files:
        ext = fp.suffix
        name_stem = fp.stem
        if "@" in name_stem:
            group, _, key = name_stem.partition("@")
        else:
            group, key = name_stem, ""
        recorder_name = ext_map.get(ext, (ext.lstrip("."), ""))[0] if ext else ""
        stat = fp.stat()
        size = _human_size(stat.st_size)
        modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
        table.add_row(
            group,
            key,
            Text(recorder_name, style=colour_map.get(recorder_name, MUTED)),
            size,
            modified,
        )

    console.print(table)


@cli.command(name="clean")
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False, path_type=Path))
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
        return

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
        f"\n[bold {CREATED}]Removed {n} .ditto/ director{'y' if n == 1 else 'ies'}.[/bold {CREATED}]"
    )


@cli.command(name="status")
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False, path_type=Path))
def cmd_status(path: Path):
    """Show aggregate statistics for snapshots under PATH.

    \b
    Examples:
      ditto status
      ditto status tests/ci/
    """
    files = _find_ditto_files(path)
    if not files:
        console.print(f"[{MUTED}]No snapshot files found.[/{MUTED}]")
        return

    render_stats(gather_stats(files, _ext_to_recorder()), console)


@cli.command(name="recorders")
def cmd_recorders():
    """List all registered recorder plugins.

    \b
    Examples:
      ditto recorders
    """
    rows: list[tuple[str, str, str]] = []
    for ep in importlib.metadata.entry_points(group="ditto_recorders"):
        try:
            recorder = ep.load()
            ext = f".{recorder.extension}"
            dist = ep.dist.name if ep.dist else "unknown"
        except Exception:
            ext = "?"
            dist = "unknown"
        rows.append((ep.name, ext, dist))

    if not rows:
        console.print(f"[{MUTED}]No recorders registered.[/{MUTED}]")
        return

    colour_map = _build_colour_map(name for name, _, _ in rows)

    lines = Text()
    lines.append("\n")
    lines.append(f"  {'Name':<12}{'Extension':<14}{'Source'}\n", style=f"bold {HEADER}")
    for name, ext, dist in sorted(rows):
        lines.append(f"  {name:<12}", style=colour_map.get(name, MUTED))
        lines.append(f"{ext:<14}", style=TEXT)
        lines.append(f"{dist}\n", style=MUTED)

    console.print(Panel(
        lines,
        title=f"[bold {TITLE}]registered recorders[/bold {TITLE}]",
        border_style=TITLE,
        expand=False,
    ))
