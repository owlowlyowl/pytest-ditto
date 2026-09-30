"""Rich presentation shared by the CLI commands."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime

from rich import box
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ditto._inventory import location_key
from ditto._lockfile import LockEntry
from ditto._manifest import Manifest, ManifestEntry
from pathlib import Path
from ditto._theme import (
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
    TEAL,
    SKY,
    MAUVE,
    FLAMINGO,
)
from ._data import (
    RecorderInfo,
    _parse_snapshot_name,
    _mark_for,
    _recorder_name,
    _human_size,
)
from ._diagnostics import CheckResult, LintIssue
from ._summary import SnapshotStats, _format_size_summary, _sum_sizes

_RECORDER_PALETTE = (ACCENT, UPDATED, CREATED, WOULD_PRUNE, TEAL, SKY, MAUVE, FLAMINGO)


def _build_colour_map(recorder_names: Iterable[str]) -> dict[str, str]:
    """Map recorder names to palette colours by sorted order — deterministic."""
    return {
        name: _RECORDER_PALETTE[i % len(_RECORDER_PALETTE)]
        for i, name in enumerate(sorted(set(recorder_names)))
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


def _table(title: str, **kwargs) -> Table:
    """A consistent, quiet frame with literal titles and wrapping cells."""
    return Table(
        title=Text(title, style=f"bold {TITLE}"),
        title_justify="left",
        box=box.ROUNDED,
        border_style=MUTED,
        header_style=f"bold {HEADER}",
        **kwargs,
    )


def _location_label(location: str) -> Text:
    """Shorten local locations relative to cwd; leave remote URIs intact."""
    if "://" not in location or location.startswith("file://"):
        path = Path(location_key(location))
        try:
            location = str(path.relative_to(Path.cwd())) or "."
        except ValueError:
            location = str(path)
    return Text(location, style=PATH, overflow="fold")


def _render_snapshots(
    manifest: Manifest,
    em: Mapping[str, RecorderInfo],
    identities: Mapping[tuple[str, str], LockEntry] | None,
    console: Console,
    *,
    flat: bool = False,
) -> None:
    """Group by target and exact lock file path, preserving one row per snapshot.

    Only split the first node-id separator: parameter values may themselves
    contain ``::``, slashes, brackets, or dots. Unlocked labels stay intact.
    """
    colours = _build_colour_map(
        _recorder_name(_parse_snapshot_name(e.storage_key)[2], em)
        for backend in manifest
        for e in backend.entries
    )
    table = _table("ditto snapshots")
    table.add_column(
        "Test" if flat else "Target / test", style=TEXT, overflow="fold", ratio=3
    )
    narrow = console.width < 60
    compact = console.width < 100
    if not narrow:
        table.add_column("Key", overflow="fold", ratio=1)
        table.add_column("Recorder", overflow="fold")
    if compact:
        table.add_column("Details", style=MUTED, overflow="fold")
    else:
        table.add_column("Size", justify="right", style=MUTED, no_wrap=True)
        table.add_column("Modified", style=MUTED, no_wrap=True)
    empty = [""] * (len(table.columns) - 1)
    for backend in sorted(manifest, key=lambda b: b.location):
        if not backend.entries:
            continue
        location = _location_label(backend.location)
        location.stylize("bold")
        table.add_row(location, *empty)
        groups: dict[str, list[tuple[Text, Text, ManifestEntry]]] = {}
        for entry in sorted(backend.entries, key=lambda e: e.storage_key):
            test, key = _test_and_key(backend.location, entry.storage_key, identities)
            locked = (
                identities.get((location_key(backend.location), entry.storage_key))
                if identities is not None
                else None
            )
            parent, separator, leaf = (
                locked.nodeid.partition("::") if locked else ("", "", "")
            )
            if not flat and separator:
                test = Text(leaf, overflow="fold")
            else:
                parent = ""
            groups.setdefault(parent, []).append((test, key, entry))
        for parent, rows in sorted(groups.items()):
            if parent:
                table.add_row(Text(parent, style=PATH, overflow="fold"), *empty)
            for index, (test, key, entry) in enumerate(rows):
                label: RenderableType = test
                if not flat:
                    label = Table.grid(padding=0)
                    label.add_column(width=3, no_wrap=True)
                    label.add_column(overflow="fold")
                    branch = "└─ " if index == len(rows) - 1 else "├─ "
                    label.add_row(Text(branch, style=MUTED), test)
                recorder = _recorder_name(
                    _parse_snapshot_name(entry.storage_key)[2], em
                )
                date = (
                    datetime.fromtimestamp(entry.modified).strftime("%Y-%m-%d")
                    if entry.modified is not None
                    else "—"
                )
                size = _human_size(entry.size_bytes)
                details = (
                    [Text(size if date == "—" else f"{size}\n{date}")]
                    if compact
                    else [Text(size), Text(date)]
                )
                recorder_text = Text(
                    recorder or "unknown", style=colours.get(recorder, MUTED)
                )
                if narrow:
                    metadata = Group(
                        Text.assemble(("Key: ", MUTED), key), recorder_text, *details
                    )
                    table.add_row(label, metadata)
                else:
                    table.add_row(label, key, recorder_text, *details)
        table.add_section()
    count = sum(len(b.entries) for b in manifest)
    targets = sum(bool(b.entries) for b in manifest)
    table.caption = Text(
        f"{count} snapshot{'s' if count != 1 else ''} · "
        f"{targets} target{'s' if targets != 1 else ''}",
        style=MUTED,
    )
    table.caption_justify = "left"
    console.print(table)


def render_stats(stats: SnapshotStats, console: Console) -> None:
    """Render responsive summary, recorder counts, and literal file identities."""
    colours = _build_colour_map(stats.by_recorder)
    totals = Text.assemble(
        (str(stats.total_count), f"bold {TEXT}"),
        (" snapshots  ·  ", MUTED),
        (_format_size_summary(stats.total_size), f"bold {TEXT}"),
    )
    breakdown = Table(box=None, padding=(0, 1), header_style=f"bold {HEADER}")
    breakdown.add_column("Recorder")
    breakdown.add_column("Snapshots", justify="right")
    breakdown.add_column("Size", justify="right", style=MUTED)
    for name, recorder in sorted(stats.by_recorder.items()):
        breakdown.add_row(
            Text(name or "unknown", style=colours.get(name, MUTED)),
            str(recorder.count),
            _format_size_summary(recorder.size),
        )
    content = [totals, Text(""), breakdown]
    for label, value in (("Oldest", stats.oldest), ("Newest", stats.newest)):
        if value:
            date = datetime.fromtimestamp(value[0]).strftime("%Y-%m-%d")
            content.extend([
                Text(""),
                Text(f"{label} · {date}", style=MUTED),
                Text(value[1], style=PATH, overflow="fold"),
            ])
    console.print(
        Panel(
            Group(*content),
            title=Text("ditto status", style=f"bold {TITLE}"),
            title_align="left",
            border_style=MUTED,
            expand=False,
        )
    )


def _render_recorders(infos: list[RecorderInfo], console: Console) -> None:
    colours = _build_colour_map(info.name for info in infos)
    table = _table("registered recorders")
    for column in ("Name", "Mark", "Identifier", "Source"):
        table.add_column(column, overflow="fold")
    for info in sorted(infos, key=lambda i: (i.name, i.package)):
        table.add_row(
            Text(info.name, style=colours.get(info.name, MUTED)),
            Text(_mark_for(info.name)),
            Text(info.identifier),
            Text(info.package, style=MUTED),
        )
    console.print(table)


def _render_doctor(checks: list[CheckResult], console: Console) -> None:
    table = _table(
        "ditto doctor",
    )
    table.add_column("Check", style=TEXT, overflow="fold")
    table.add_column("Status", justify="center")
    table.add_column("Detail", style=MUTED)

    for check in checks:
        status = (
            Text("PASS", style=f"bold {CREATED}")
            if check.ok
            else Text("FAIL", style=f"bold {PRUNED}")
        )
        table.add_row(Text(check.name), status, Text(check.detail, overflow="fold"))

    console.print(table)


def _render_lint_issues(issues: list[LintIssue], console: Console) -> None:
    table = _table(
        "ditto lint",
    )
    table.add_column("File", style=PATH)
    table.add_column("Issue", style=f"bold {PRUNED}")

    location = None
    for issue in sorted(issues, key=lambda i: (i.location, i.filename)):
        if issue.location and issue.location != location:
            if location is not None:
                table.add_section()
            table.add_row(_location_label(issue.location), "")
            location = issue.location
        table.add_row(
            Text(issue.filename, overflow="fold"), Text(issue.issue, overflow="fold")
        )

    console.print(table)


def _render_stats_table(
    dir_stats: list[tuple[str, SnapshotStats]], console: Console
) -> None:
    all_names = {name for _, s in dir_stats for name in s.by_recorder}
    colour_map = _build_colour_map(all_names)

    table = _table(
        "ditto stats",
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
                f"{name or 'unknown'}×{recorder.count}",
                style=colour_map.get(name, MUTED),
            )
        table.add_row(
            _location_label(d),
            str(s.total_count),
            _format_size_summary(s.total_size),
            recorder_text,
        )

    table.columns[1].footer = str(total_count)
    table.columns[2].footer = _format_size_summary(total_size)

    console.print(table)
