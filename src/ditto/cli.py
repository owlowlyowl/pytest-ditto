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
doctor      Run health checks on the ditto installation and plugins.
lint        Check snapshot files for naming, format, and integrity issues.
stats       Show per-directory snapshot usage breakdown.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import shutil
import subprocess
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ._theme import (
    CREATED,
    UPDATED,
    UNUSED,
    PRUNED,
    TITLE,
    HEADER,
    MUTED,
    ACCENT,
    PATH,
    TEXT,
    SUBTEXT1,
    TEAL,
    SKY,
    MAUVE,
    FLAMINGO,
)
from ._manifest import Manifest, ManifestEntry
from ._cli_introspect import IntrospectError, run_introspect


console = Console()

_RECORDER_PALETTE = (
    ACCENT,  # peach
    UPDATED,  # blue
    CREATED,  # green
    UNUSED,  # yellow
    TEAL,
    SKY,
    MAUVE,
    FLAMINGO,
)


def _build_colour_map(recorder_names: Iterable[str]) -> dict[str, str]:
    """Map recorder names to palette colours by sorted order — deterministic."""
    return {
        name: _RECORDER_PALETTE[i % len(_RECORDER_PALETTE)]
        for i, name in enumerate(sorted(recorder_names))
    }


def _parse_snapshot_name(filename: str) -> tuple[str, str, str]:
    """Parse a snapshot filename into (name, key, ext).

    File-backend snapshots are named `module.group@key.ext`, so the part before
    `@` carries the dotted module prefix (e.g. `tests.test_api.TestCase`).
    The ext may contain dots (e.g. `pandas.csv`).
    Returns ext with a leading dot (e.g. `.pandas.csv`), or `""` if absent.
    """
    group, _, rest = filename.partition("@")
    if not rest:
        return filename, "", ""
    key, dot, ext_suffix = rest.partition(".")
    return group, key, f"{dot}{ext_suffix}"


def _find_ditto_dirs(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob(".ditto") if p.is_dir())


def _inventory_or_exit(path: Path) -> Manifest:
    """Run the introspection pass for PATH, or print the error and exit(1).

    Always introspects: the pytest pass resolves real fixtures and per-test
    record(target=...) marks, so the inventory covers local file://, remote, and
    fixture-defined backends with nothing inferred from static config.
    """
    try:
        return run_introspect(path)
    except IntrospectError as exc:
        console.print(f"[bold {PRUNED}]Introspection failed:[/bold {PRUNED}] {exc}")
        sys.exit(1)


def _entries(manifest: Manifest) -> list[ManifestEntry]:
    """Flatten all entries across the manifest's backends."""
    return [e for b in manifest for e in b.entries]


@dataclass(frozen=True)
class RecorderInfo:
    name: str  # e.g. "pandas_parquet"
    extension: str  # e.g. ".pandas.parquet"
    package: str  # e.g. "pytest-ditto-pandas"


def _load_recorder_infos() -> list[RecorderInfo]:
    """Load all registered recorder entry points."""
    infos = []
    for ep in importlib.metadata.entry_points(group="ditto_recorders"):
        try:
            recorder = ep.load()
            ext = f".{recorder.extension}"
            dist = ep.dist.name if ep.dist else "unknown"
        except Exception:
            ext, dist = "?", "unknown"
        infos.append(RecorderInfo(name=ep.name, extension=ext, package=dist))
    return infos


def _ext_map(infos: list[RecorderInfo]) -> dict[str, RecorderInfo]:
    """Pure: derive extension → RecorderInfo lookup from a list of infos."""
    return {info.extension: info for info in infos}


def _recorder_name(ext: str, ext_map: Mapping[str, RecorderInfo]) -> str:
    """Map a parsed extension to its recorder name, falling back to the bare ext."""
    if ext in ext_map:
        return ext_map[ext].name
    return ext.lstrip(".")


def _human_size(n: int) -> str:
    value: float = n
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{n} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


# ── Status aggregation ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SnapshotStats:
    total_count: int
    total_size: int
    by_recorder: Mapping[str, tuple[int, int]]  # name → (count, bytes)
    oldest: tuple[float, str] | None
    newest: tuple[float, str] | None


def gather_stats(
    entries: list[ManifestEntry], ext_map: Mapping[str, RecorderInfo]
) -> SnapshotStats:
    """Aggregate snapshot statistics from a list of ManifestEntry items."""
    total_size = 0
    by_recorder: dict[str, tuple[int, int]] = {}
    oldest: tuple[float, str] | None = None
    newest: tuple[float, str] | None = None

    for entry in entries:
        total_size += entry.size_bytes
        _, _, ext = _parse_snapshot_name(entry.storage_key)
        recorder_name = _recorder_name(ext, ext_map)
        count, total = by_recorder.get(recorder_name, (0, 0))
        by_recorder[recorder_name] = (count + 1, total + entry.size_bytes)

        if entry.modified is not None:
            if oldest is None or entry.modified < oldest[0]:
                oldest = (entry.modified, entry.storage_key)
            if newest is None or entry.modified > newest[0]:
                newest = (entry.modified, entry.storage_key)

    return SnapshotStats(
        total_count=len(entries),
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
    name_w = max(len(name) for name in stats.by_recorder.keys())
    count_w = max(len(str(c)) for c, _ in stats.by_recorder.values())
    size_w = max(len(_human_size(s)) for _, s in stats.by_recorder.values())
    for name, (count, sz) in sorted(stats.by_recorder.items()):
        lines.append(f"    {name:<{name_w}}", style=colour_map.get(name, MUTED))
        lines.append(f"  {count:>{count_w}}  ", style=TEXT)
        lines.append(f"{_human_size(sz):>{size_w}}\n", style=MUTED)

    if stats.oldest and stats.newest:
        lines.append("\n")
        oldest_date = datetime.fromtimestamp(stats.oldest[0]).strftime("%Y-%m-%d")
        newest_date = datetime.fromtimestamp(stats.newest[0]).strftime("%Y-%m-%d")
        lines.append("  Oldest  ", style=MUTED)
        lines.append(f"{stats.oldest[1]}  ", style=PATH)
        lines.append(f"{oldest_date}\n", style=MUTED)
        lines.append("  Newest  ", style=MUTED)
        lines.append(f"{stats.newest[1]}  ", style=PATH)
        lines.append(f"{newest_date}", style=MUTED)

    console.print(
        Panel(
            lines,
            title=f"[bold {TITLE}]ditto status[/bold {TITLE}]",
            border_style=TITLE,
            expand=False,
        )
    )


# ── CLI commands ──────────────────────────────────────────────────────────────


@click.group()
def cli():
    """pytest-ditto snapshot management."""


@cli.command(
    name="run",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
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


@cli.command(
    name="update",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
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


@cli.command(
    name="prune",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
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
            f"Snapshots for skipped tests will be treated as unused and"
            f" deleted.[/{SUBTEXT1}]",
            highlight=False,
        )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--ditto-prune", *pytest_args],
        check=False,
    )
    sys.exit(result.returncode)


@cli.command(name="list")
@click.argument(
    "path", default=".", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
def cmd_list(path: Path):
    """List all snapshot files under PATH (default: current directory).

    \b
    Examples:
      ditto list
      ditto list tests/ci/
    """
    manifest = _inventory_or_exit(path)
    entries = _entries(manifest)
    if not entries:
        console.print(f"[{MUTED}]No snapshot files found.[/{MUTED}]")
        sys.exit(1)

    infos = _load_recorder_infos()
    em = _ext_map(infos)
    colour_map = _build_colour_map(info.name for info in infos)

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

    for entry in entries:
        group, key, ext = _parse_snapshot_name(entry.storage_key)
        recorder_name = _recorder_name(ext, em)
        modified = (
            datetime.fromtimestamp(entry.modified).strftime("%Y-%m-%d")
            if entry.modified is not None
            else "—"
        )
        table.add_row(
            group,
            key,
            Text(recorder_name, style=colour_map.get(recorder_name, MUTED)),
            _human_size(entry.size_bytes),
            modified,
        )

    console.print(table)


@cli.command(name="clean")
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


@cli.command(name="status")
@click.argument(
    "path", default=".", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
def cmd_status(path: Path):
    """Show aggregate statistics for snapshots under PATH.

    \b
    Examples:
      ditto status
      ditto status tests/ci/
    """
    manifest = _inventory_or_exit(path)
    entries = _entries(manifest)
    if not entries:
        console.print(f"[{MUTED}]No snapshot files found.[/{MUTED}]")
        sys.exit(1)

    render_stats(gather_stats(entries, _ext_map(_load_recorder_infos())), console)


def _render_recorders(infos: list[RecorderInfo], console: Console) -> None:
    """Build and print the registered recorders panel."""
    colour_map = _build_colour_map(info.name for info in infos)
    name_w = max(len("Name"), max(len(i.name) for i in infos))
    ext_w = max(len("Extension"), max(len(i.extension) for i in infos))

    lines = Text()
    lines.append("\n")
    lines.append(
        f"  {'Name':<{name_w}}  {'Extension':<{ext_w}}  {'Source'}\n",
        style=f"bold {HEADER}",
    )
    for info in sorted(infos, key=lambda i: i.name):
        lines.append(
            f"  {info.name:<{name_w}}  ", style=colour_map.get(info.name, MUTED)
        )
        lines.append(f"{info.extension:<{ext_w}}  ", style=TEXT)
        lines.append(f"{info.package}\n", style=MUTED)

    console.print(
        Panel(
            lines,
            title=f"[bold {TITLE}]registered recorders[/bold {TITLE}]",
            border_style=TITLE,
            expand=False,
        )
    )


@cli.command(name="recorders")
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


# ── Doctor / Lint / Stats data types ──────────────────────────────────────────


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class LintIssue:
    filename: str
    issue: str


# ── Doctor / Lint / Stats pure core ───────────────────────────────────────────


def _doctor_checks() -> list[CheckResult]:
    """Return health-check results without any I/O."""
    results: list[CheckResult] = []

    results.append(
        CheckResult(
            name="pytest importable",
            ok=importlib.util.find_spec("pytest") is not None,
            detail="",
        )
    )

    registered = any(
        ep.name == "ditto" for ep in importlib.metadata.entry_points(group="pytest11")
    )
    results.append(
        CheckResult(name="ditto plugin registered", ok=registered, detail="")
    )

    for ep in importlib.metadata.entry_points(group="ditto_recorders"):
        try:
            ep.load()
            results.append(CheckResult(name=f"recorder: {ep.name}", ok=True, detail=""))
        except Exception as exc:
            results.append(
                CheckResult(name=f"recorder: {ep.name}", ok=False, detail=str(exc))
            )

    for ep in importlib.metadata.entry_points(group="ditto_marks"):
        try:
            ep.load()
            results.append(CheckResult(name=f"mark: {ep.name}", ok=True, detail=""))
        except Exception as exc:
            results.append(
                CheckResult(name=f"mark: {ep.name}", ok=False, detail=str(exc))
            )

    return results


def _find_lint_issues(
    entries: list[ManifestEntry], em: Mapping[str, RecorderInfo]
) -> list[LintIssue]:
    """Return lint issues for inventory entries without further I/O."""
    issues: list[LintIssue] = []
    for entry in entries:
        _, key, ext = _parse_snapshot_name(entry.storage_key)
        if key == "":
            issues.append(
                LintIssue(filename=entry.storage_key, issue="Malformed name (missing @)")
            )
        elif ext not in em:
            issues.append(
                LintIssue(filename=entry.storage_key, issue=f"Unknown extension: {ext!r}")
            )
        if entry.size_bytes == 0:
            issues.append(LintIssue(filename=entry.storage_key, issue="Empty file"))
    return issues


# ── Doctor / Lint / Stats rendering ───────────────────────────────────────────


def _render_doctor(checks: list[CheckResult], console: Console) -> None:
    table = Table(
        title=f"[bold {TITLE}]ditto doctor[/bold {TITLE}]",
        border_style=MUTED,
        header_style=f"bold {HEADER}",
        show_header=True,
    )
    table.add_column("Check", style=TEXT)
    table.add_column("Status", justify="center")
    table.add_column("Detail", style=MUTED)

    for check in checks:
        status = (
            Text("✓", style=f"bold {CREATED}")
            if check.ok
            else Text("✗", style=f"bold {PRUNED}")
        )
        table.add_row(check.name, status, check.detail)

    console.print(table)


def _render_lint_issues(issues: list[LintIssue], console: Console) -> None:
    table = Table(
        title=f"[bold {TITLE}]ditto lint[/bold {TITLE}]",
        border_style=MUTED,
        header_style=f"bold {HEADER}",
        show_header=True,
    )
    table.add_column("File", style=PATH)
    table.add_column("Issue", style=f"bold {PRUNED}")

    for issue in issues:
        table.add_row(issue.filename, issue.issue)

    console.print(table)


def _render_stats_table(
    dir_stats: list[tuple[str, SnapshotStats]], console: Console
) -> None:
    all_names = {name for _, s in dir_stats for name in s.by_recorder}
    colour_map = _build_colour_map(all_names)

    table = Table(
        title=f"[bold {TITLE}]ditto stats[/bold {TITLE}]",
        border_style=MUTED,
        header_style=f"bold {HEADER}",
        show_header=True,
        show_footer=True,
    )
    table.add_column(
        "Directory", style=PATH, footer_style=f"bold {HEADER}", footer="TOTAL"
    )
    table.add_column(
        "Snapshots", justify="right", style=TEXT, footer_style=f"bold {TEXT}"
    )
    table.add_column("Size", justify="right", style=MUTED, footer_style=f"bold {MUTED}")
    table.add_column("Recorders", footer_style=MUTED)

    total_count = sum(s.total_count for _, s in dir_stats)
    total_size = sum(s.total_size for _, s in dir_stats)

    for d, s in dir_stats:
        recorder_text = Text()
        for i, (name, (cnt, _sz)) in enumerate(sorted(s.by_recorder.items())):
            if i:
                recorder_text.append("  ")
            recorder_text.append(f"{name}×{cnt}", style=colour_map.get(name, MUTED))
        table.add_row(
            d, str(s.total_count), _human_size(s.total_size), recorder_text
        )

    table.columns[1].footer = str(total_count)
    table.columns[2].footer = _human_size(total_size)

    console.print(table)


# ── New CLI commands ───────────────────────────────────────────────────────────


@cli.command(name="doctor")
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


@cli.command(name="lint")
@click.argument(
    "path", default=".", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
def cmd_lint(path: Path):
    """Check snapshot files for naming issues, unknown formats, and empty files.

    \b
    Examples:
      ditto lint
      ditto lint tests/ci/
    """
    manifest = _inventory_or_exit(path)
    issues = _find_lint_issues(_entries(manifest), _ext_map(_load_recorder_infos()))
    if not issues:
        console.print(f"[{MUTED}]All snapshots are valid.[/{MUTED}]")
        return
    _render_lint_issues(issues, console)
    sys.exit(1)


@cli.command(name="stats")
@click.argument(
    "path", default=".", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
def cmd_stats(path: Path):
    """Show per-directory snapshot usage breakdown.

    \b
    Examples:
      ditto stats
      ditto stats tests/ci/
    """
    manifest = _inventory_or_exit(path)
    if not manifest:
        console.print(f"[{MUTED}]No snapshot files found.[/{MUTED}]")
        sys.exit(1)
    em = _ext_map(_load_recorder_infos())
    dir_stats = [(b.location, gather_stats(b.entries, em)) for b in manifest]
    _render_stats_table(dir_stats, console)
