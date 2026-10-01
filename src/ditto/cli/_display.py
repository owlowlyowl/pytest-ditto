"""Rich rendering for the CLI commands."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path

import click
from rich import box
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .._inventory import location_key
from .._lockfile import LockEntry
from .._manifest import BackendManifest, Manifest, ManifestEntry
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


# Below this width a snapshot's key and recorder no longer fit beside its
# identity, so the metadata moves into a single cell underneath it.
NARROW = 60
# Below this width the size and the date share a cell instead of a column each.
COMPACT = 80

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


def _table(title: str, **kwargs: object) -> Table:
    """A table with this project's frame and a literal, left-aligned title.

    Columns holding a name set `overflow="fold"`, so a long one wraps in the
    middle rather than being truncated from the end: the part that tells two
    rows apart stays visible.
    """
    return Table(
        title=Text(title, style=f"bold {TITLE}"),
        title_justify="left",
        box=box.ROUNDED,
        border_style=MUTED,
        header_style=f"bold {HEADER}",
        **kwargs,  # type: ignore[arg-type]
    )


def _heading_row(label: Text, column_count: int) -> tuple[RenderableType, ...]:
    """A row holding a group heading in the first column and nothing elsewhere."""
    return (label, *(Text("") for _ in range(column_count - 1)))


def _location_label(location: str) -> Text:
    """A target's location relative to the current directory, never absolute.

    A local directory is shown as the path someone would type; a remote URI is
    shown whole, because there is nothing to shorten it relative to.
    """
    if "://" in location and not location.startswith("file://"):
        return Text(location, style=PATH, overflow="fold")
    try:
        relative = Path(location_key(location)).relative_to(Path.cwd())
    except ValueError:
        return Text(location, style=PATH, overflow="fold")
    return Text(str(relative) or ".", style=PATH, overflow="fold")


def _test_and_key(
    location: str,
    storage_key: str,
    identities: Mapping[tuple[str, str], LockEntry] | None,
) -> tuple[Text, Text, LockEntry | None]:
    """The test's node id and key from the lock, else the name's labels.

    Looked up by the backend's location as well as the name: the same name
    under another target is a different snapshot. A name the lock doesn't
    record there (an orphan, or a snapshot recorded since the last
    `ditto lock`) is marked when there is a lock to check against. Both are
    `Text`, so Rich never reads a test name or key as markup.
    """
    label, key, _ = _parse_snapshot_name(storage_key)
    if identities is None:
        return Text(label, overflow="fold"), Text(key), None
    entry = identities.get((location_key(location), storage_key))
    if entry is not None:
        return Text(entry.nodeid, overflow="fold"), Text(entry.key), entry
    return Text.assemble((label, TEXT), ("  not in lock", MUTED)), Text(key), None


def _modified(modified: float | None) -> str:
    """A snapshot's last-modified date, or a dash when the backend reports none."""
    if modified is None:
        return "—"
    return datetime.fromtimestamp(modified).strftime("%Y-%m-%d")


def _metadata_cells(
    entry: ManifestEntry, compact: bool
) -> list[RenderableType]:
    """A snapshot's size and date, as one cell or two depending on the width."""
    size = Text(_human_size(entry.size_bytes), style=MUTED, no_wrap=True)
    date = Text(_modified(entry.modified), style=MUTED, no_wrap=True)
    if not compact:
        return [size, date]
    if date.plain == "—":
        return [size]
    return [Text.assemble((size.plain, MUTED), "\n", (date.plain, MUTED))]


def _branch(label: Text, last: bool) -> Table:
    """A tree branch: a `├─` or `└─` marker beside one snapshot's name."""
    grid = Table.grid(padding=0)
    grid.add_column(width=3, no_wrap=True)
    grid.add_column(overflow="fold")
    grid.add_row(Text("└─ " if last else "├─ ", style=MUTED), label)
    return grid


def _by_test_file(
    entries: Sequence[ManifestEntry],
    location: str,
    identities: Mapping[tuple[str, str], LockEntry] | None,
    *,
    flat: bool,
) -> list[tuple[str, list[tuple[Text, Text, ManifestEntry]]]]:
    """Group one target's snapshots by the test file the lock records them in.

    Only the first `::` of a node id is split off: a parametrize ID can contain
    `::`, slashes, brackets and dots of its own. A snapshot the lock doesn't
    record has no file to group it under, so it keeps an empty parent and is
    listed after the files. `flat` skips the split, so every row carries the
    whole node id.
    """
    groups: dict[str, list[tuple[Text, Text, ManifestEntry]]] = {}
    for entry in sorted(entries, key=lambda e: e.storage_key):
        test, key, locked = _test_and_key(location, entry.storage_key, identities)
        parent, separator, leaf = (
            locked.nodeid.partition("::") if locked else ("", "", "")
        )
        if locked and not flat:
            test = Text(leaf, overflow="fold")
        groups.setdefault(parent, []).append((test, key, entry))
    return sorted(groups.items(), key=lambda item: (item[0] == "", item[0]))


def _render_snapshots(
    manifest: Manifest,
    identities: Mapping[tuple[str, str], LockEntry] | None,
    infos: list[RecorderInfo],
    console: Console,
    *,
    flat: bool = False,
) -> None:
    """Print every snapshot in the manifest, grouped by target and test file.

    The grouped layout drops the repeated target and file path so the part that
    tells two rows apart — the test and its key — keeps the width. `flat` prints
    one row per snapshot with the whole node id, for grepping.
    """
    ext_map = _ext_map(infos)
    colours = _build_colour_map(
        _recorder_name(_parse_snapshot_name(e.storage_key)[2], ext_map)
        for backend in manifest
        for e in backend.entries
    )

    narrow = console.width < NARROW
    compact = console.width < COMPACT
    table = _table("ditto snapshots")
    table.add_column("Target / test", style=TEXT, overflow="fold", ratio=3)
    if not narrow:
        table.add_column("Key", overflow="fold", ratio=1)
        table.add_column("Recorder", overflow="fold")
    if compact:
        table.add_column("Details", style=MUTED, overflow="fold")
    else:
        table.add_column("Size", justify="right", style=MUTED, no_wrap=True)
        table.add_column("Modified", style=MUTED, no_wrap=True)

    for backend in sorted(manifest, key=lambda b: b.location):
        if not backend.entries:
            continue
        target = _location_label(backend.location)
        target.stylize("bold")
        table.add_row(*_heading_row(target, len(table.columns)))
        for parent, rows in _by_test_file(
            backend.entries, backend.location, identities, flat=flat
        ):
            if parent and not flat:
                table.add_row(
                    *_heading_row(
                        Text(parent, style=PATH, overflow="fold"),
                        len(table.columns),
                    )
                )
            for index, (test, key, entry) in enumerate(rows):
                label = test if flat else _branch(test, index == len(rows) - 1)
                _, _, ext = _parse_snapshot_name(entry.storage_key)
                recorder = _recorder_name(ext, ext_map)
                recorder_text = Text(
                    recorder or "unknown",
                    style=colours.get(recorder, MUTED),
                    overflow="fold",
                )
                cells: list[RenderableType]
                if narrow:
                    cells = [Group(Text.assemble(("Key: ", MUTED), key), recorder_text)]
                else:
                    cells = [key, recorder_text]
                table.add_row(label, *cells, *_metadata_cells(entry, compact))
        table.add_section()

    count = sum(len(b.entries) for b in manifest)
    targets = sum(1 for b in manifest if b.entries)
    table.caption = Text(
        f"{count} snapshot{'' if count == 1 else 's'} · "
        f"{targets} target{'' if targets == 1 else 's'}",
        style=MUTED,
    )
    table.caption_justify = "left"
    console.print(table)


def render_stats(
    stats: SnapshotStats,
    identities: Mapping[tuple[str, str], LockEntry] | None,
    console: Console,
) -> None:
    """Render a SnapshotStats value as the inventory's one summary.

    Totals, the per-recorder breakdown, and the oldest and newest snapshots
    named the way `ditto list` names them, so a figure isn't spread over two
    commands.
    """
    colour_map = _build_colour_map(stats.by_recorder.keys())

    breakdown = Table(box=None, padding=(0, 1), show_header=False)
    breakdown.add_column("Recorder", overflow="fold")
    breakdown.add_column("Snapshots", justify="right")
    breakdown.add_column("Size", justify="right", style=MUTED, no_wrap=True)
    for name, recorder in sorted(stats.by_recorder.items()):
        breakdown.add_row(
            Text(name or "unknown", style=colour_map.get(name, MUTED)),
            str(recorder.count),
            _format_size_summary(recorder.size),
        )

    content: list[RenderableType] = [
        Text.assemble(
            (str(stats.total_count), f"bold {TEXT}"),
            (" snapshots  ·  ", MUTED),
            (_format_size_summary(stats.total_size), f"bold {TEXT}"),
        ),
        Text(),
        breakdown,
    ]
    for label, extreme in (("Oldest", stats.oldest), ("Newest", stats.newest)):
        if extreme is None:
            continue
        content.append(Text())
        content.append(
            Text.assemble(
                (f"{label}  ", f"bold {MUTED}"),
                (datetime.fromtimestamp(extreme.modified).strftime("%Y-%m-%d"), MUTED),
            )
        )
        content.append(
            Text(
                _identity_label(extreme.location, extreme.storage_key, identities),
                style=PATH,
                overflow="fold",
            )
        )

    console.print(
        Panel(
            Group(*content),
            title=Text("ditto status", style=f"bold {TITLE}"),
            title_align="left",
            border_style=MUTED,
            expand=False,
        )
    )


def _identity_label(
    location: str,
    storage_key: str,
    identities: Mapping[tuple[str, str], LockEntry] | None,
) -> str:
    """The node id the lock records a snapshot under, else its storage name."""
    if identities is None:
        return storage_key
    entry = identities.get((location_key(location), storage_key))
    if entry is None:
        return storage_key
    return f"{entry.nodeid}  {entry.key}"


def _render_recorders(infos: list[RecorderInfo], console: Console) -> None:
    """Print the registered recorders, with the identifier only when it differs.

    The identifier is `.` + the name for every recorder the plugin contract
    allows, so a column of it would only cost width. One that doesn't follow
    that form still shows it.
    """
    colour_map = _build_colour_map(info.name for info in infos)
    show_identifier = any(i.identifier != f".{i.name}" for i in infos)

    table = _table("registered recorders")
    table.add_column("Name", style=TEXT, overflow="fold")
    table.add_column("Mark", overflow="fold")
    if show_identifier:
        table.add_column("Identifier", overflow="fold")
    table.add_column("Source", style=MUTED, overflow="fold")

    for info in sorted(infos, key=lambda i: i.name):
        row: list[RenderableType] = [
            Text(info.name, style=colour_map.get(info.name, MUTED)),
            Text(_mark_for(info.name)),
        ]
        if show_identifier:
            row.append(Text(info.identifier))
        row.append(Text(info.package))
        table.add_row(*row)

    console.print(table)


def _render_doctor(checks: list[CheckResult], console: Console) -> None:
    table = _table("ditto doctor")
    table.add_column("Check", style=TEXT, overflow="fold")
    table.add_column("Status", justify="center")
    table.add_column("Detail", style=MUTED, overflow="fold")

    for check in checks:
        status = (
            Text("✓", style=f"bold {CREATED}")
            if check.ok
            else Text("✗", style=f"bold {PRUNED}")
        )
        table.add_row(Text(check.name), status, Text(check.detail))

    console.print(table)


def _render_lint_issues(issues: list[LintIssue], console: Console) -> None:
    table = _table("ditto lint")
    table.add_column("File", style=PATH, overflow="fold")
    table.add_column("Issue", style=f"bold {PRUNED}", overflow="fold")

    for issue in sorted(issues, key=lambda i: i.filename):
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
    """Print where the snapshots are: a row per target, with its count and size.

    Per-recorder counts are `ditto status`'s; they are not repeated here.
    """
    table = _table("ditto stats", show_footer=True)
    table.add_column(
        "Directory",
        style=PATH,
        overflow="fold",
        footer_style=f"bold {HEADER}",
        footer="TOTAL",
    )
    table.add_column(
        "Snapshots", justify="right", style=TEXT, footer_style=f"bold {TEXT}"
    )
    table.add_column(
        "Size",
        justify="right",
        style=MUTED,
        no_wrap=True,
        footer_style=f"bold {MUTED}",
    )

    for directory, stats in dir_stats:
        table.add_row(
            _location_label(directory),
            str(stats.total_count),
            _format_size_summary(stats.total_size),
        )

    table.columns[1].footer = str(sum(s.total_count for _, s in dir_stats))
    table.columns[2].footer = _format_size_summary(
        _sum_sizes(s.total_size for _, s in dir_stats)
    )

    console.print(table)
