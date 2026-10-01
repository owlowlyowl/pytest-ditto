"""Rich rendering for the CLI commands."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .._inventory import location_key
from .._lockfile import LockEntry
from .._manifest import BackendManifest, Manifest
from .._theme import (
    CREATED,
    UPDATED,
    WOULD_PRUNE,
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
from ._data import (
    RecorderInfo,
    _ext_map,
    _human_size,
    _mark_for,
    _parse_snapshot_name,
    _recorder_name,
)
from ._diagnostics import CheckResult, LintIssue
from ._summary import SnapshotStats, _format_size_summary, _sum_sizes


# Passes a command the Console given as Click's context object, creating one
# that writes to stdout when the caller gave none.
pass_console = click.make_pass_decorator(Console, ensure=True)


_RECORDER_PALETTE = (
    ACCENT,  # peach
    UPDATED,  # blue
    CREATED,  # green
    WOULD_PRUNE,  # yellow
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


def _test_and_key(
    location: str,
    storage_key: str,
    identities: Mapping[tuple[str, str], LockEntry] | None,
) -> tuple[Text, Text]:
    """The test's node id and key from the lock, else the name's labels.

    Looked up by the backend's location as well as the name: the same name
    under another target is a different snapshot. A name the lock doesn't
    record there (an orphan, or a snapshot recorded since the last
    `ditto lock`) is marked when there is a lock to check against. Both are
    `Text`, so Rich never reads a test name or key as markup.
    """
    label, key, _ = _parse_snapshot_name(storage_key)
    if identities is None:
        return Text(label), Text(key)
    entry = identities.get((location_key(location), storage_key))
    if entry is not None:
        return Text(entry.nodeid), Text(entry.key)
    return Text.assemble(label, ("  not in lock", MUTED)), Text(key)


def _render_snapshots(
    manifest: Manifest,
    identities: Mapping[tuple[str, str], LockEntry] | None,
    infos: list[RecorderInfo],
    console: Console,
) -> None:
    """Print a table of every snapshot in the manifest."""
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

    rows = [(b.location, e) for b in manifest for e in b.entries]
    for location, entry in rows:
        _, _, ext = _parse_snapshot_name(entry.storage_key)
        recorder_name = _recorder_name(ext, em)
        modified = (
            datetime.fromtimestamp(entry.modified).strftime("%Y-%m-%d")
            if entry.modified is not None
            else "—"
        )
        test, key = _test_and_key(location, entry.storage_key, identities)
        table.add_row(
            test,
            key,
            Text(recorder_name, style=colour_map.get(recorder_name, MUTED)),
            _human_size(entry.size_bytes),
            modified,
        )

    console.print(table)


def render_stats(stats: SnapshotStats, console: Console) -> None:
    """Render a SnapshotStats value as a Rich panel."""
    colour_map = _build_colour_map(stats.by_recorder.keys())

    lines = Text()
    lines.append("  Total snapshots  ", style=MUTED)
    lines.append(f"{stats.total_count}\n", style=f"bold {TEXT}")
    lines.append("  Total size       ", style=MUTED)
    lines.append(f"{_format_size_summary(stats.total_size)}\n", style=f"bold {TEXT}")
    lines.append("\n")
    lines.append("  By recorder:\n", style=f"bold {HEADER}")
    name_w = max(len(name) for name in stats.by_recorder.keys())
    count_w = max(len(str(recorder.count)) for recorder in stats.by_recorder.values())
    size_w = max(
        len(_format_size_summary(recorder.size))
        for recorder in stats.by_recorder.values()
    )
    for name, recorder in sorted(stats.by_recorder.items()):
        lines.append(f"    {name:<{name_w}}", style=colour_map.get(name, MUTED))
        lines.append(f"  {recorder.count:>{count_w}}  ", style=TEXT)
        lines.append(
            f"{_format_size_summary(recorder.size):>{size_w}}\n",
            style=MUTED,
        )

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


def _render_recorders(infos: list[RecorderInfo], console: Console) -> None:
    """Build and print the registered recorders panel."""
    colour_map = _build_colour_map(info.name for info in infos)
    name_w = max(len("Name"), max(len(i.name) for i in infos))
    mark_w = max(len("Mark"), max(len(_mark_for(i.name)) for i in infos))
    ext_w = max(len("Identifier"), max(len(i.identifier) for i in infos))

    lines = Text()
    lines.append("\n")
    lines.append(
        f"  {'Name':<{name_w}}  {'Mark':<{mark_w}}  {'Identifier':<{ext_w}}  Source\n",
        style=f"bold {HEADER}",
    )
    for info in sorted(infos, key=lambda i: i.name):
        lines.append(
            f"  {info.name:<{name_w}}  ", style=colour_map.get(info.name, MUTED)
        )
        lines.append(f"{_mark_for(info.name):<{mark_w}}  ", style=TEXT)
        lines.append(f"{info.identifier:<{ext_w}}  ", style=TEXT)
        lines.append(f"{info.package}\n", style=MUTED)

    console.print(
        Panel(
            lines,
            title=f"[bold {TITLE}]registered recorders[/bold {TITLE}]",
            border_style=TITLE,
            expand=False,
        )
    )


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
        table.add_row(Text(check.name), status, Text(check.detail))

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
        table.add_row(Text(issue.filename), Text(issue.issue))

    console.print(table)


def _render_unreadable_backends(
    backends: list[BackendManifest], console: Console
) -> None:
    """Print each backend the live pass couldn't read, with its error."""
    for backend in backends:
        console.print(
            Text.assemble(
                ("Could not read ", f"bold {PRUNED}"),
                (backend.location, PATH),
                f": {backend.error}",
            )
        )
    n = len(backends)
    console.print(
        Text(
            f"Inventory incomplete: {n} backend{'s' if n != 1 else ''} "
            "could not be read.",
            style=PRUNED,
        )
    )


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
    total_size = _sum_sizes(s.total_size for _, s in dir_stats)

    for d, s in dir_stats:
        recorder_text = Text()
        for i, (name, recorder) in enumerate(sorted(s.by_recorder.items())):
            if i:
                recorder_text.append("  ")
            recorder_text.append(
                f"{name}×{recorder.count}",
                style=colour_map.get(name, MUTED),
            )
        table.add_row(
            Text(d),
            str(s.total_count),
            _format_size_summary(s.total_size),
            recorder_text,
        )

    table.columns[1].footer = str(total_count)
    table.columns[2].footer = _format_size_summary(total_size)

    console.print(table)
