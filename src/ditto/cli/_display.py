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
from ._summary import (
    Extremes,
    LocatedEntry,
    SnapshotStats,
    _format_size_summary,
    _sum_sizes,
)


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
    # Fold rather than cut a long test or key: the end of a node id is the part
    # that tells two parametrized cases apart.
    table.add_column("Test", style=TEXT, overflow="fold")
    table.add_column("Key", style=SUBTEXT1, overflow="fold")
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


def _named(
    located: LocatedEntry,
    identities: Mapping[tuple[str, str], LockEntry] | None,
    ext_map: Mapping[str, RecorderInfo],
) -> Text:
    """A snapshot named as `ditto list` names it: test, key and recorder."""
    _, _, ext = _parse_snapshot_name(located.entry.storage_key)
    test, key = _test_and_key(located.location, located.entry.storage_key, identities)
    key.stylize(SUBTEXT1)
    return Text.assemble(
        test, "  ", key, "  ", (_recorder_name(ext, ext_map), MUTED), style=TEXT
    )


def _date(located: LocatedEntry) -> str:
    modified = located.entry.modified
    if modified is None:
        return "—"
    return datetime.fromtimestamp(modified).strftime("%Y-%m-%d")


def render_stats(
    stats: SnapshotStats,
    extremes: Extremes | None,
    identities: Mapping[tuple[str, str], LockEntry] | None,
    ext_map: Mapping[str, RecorderInfo],
    console: Console,
) -> None:
    """Render a SnapshotStats value, and the oldest and newest snapshots, as a panel."""
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

    if extremes is not None:
        lines.append("\n")
        lines.append(f"  Oldest  {_date(extremes.oldest)}  ", style=MUTED)
        lines.append_text(_named(extremes.oldest, identities, ext_map))
        lines.append("\n")
        lines.append(f"  Newest  {_date(extremes.newest)}  ", style=MUTED)
        lines.append_text(_named(extremes.newest, identities, ext_map))

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

    # A table sizes and folds its columns to the width it's given, so one long
    # name can't push the other rows' columns onto a second line.
    table = Table(box=None, header_style=f"bold {HEADER}", padding=(0, 2, 0, 1))
    table.add_column("Name", overflow="fold")
    table.add_column("Mark", style=TEXT, overflow="fold")
    table.add_column("Identifier", style=TEXT, overflow="fold")
    table.add_column("Source", style=MUTED, overflow="fold")
    for info in sorted(infos, key=lambda i: i.name):
        table.add_row(
            Text(info.name, style=colour_map.get(info.name, MUTED)),
            Text(_mark_for(info.name)),
            Text(info.identifier),
            Text(info.package),
        )

    console.print(
        Panel(
            table,
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
