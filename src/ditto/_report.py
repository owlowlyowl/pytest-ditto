from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import TypeVar

from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ._theme import (
    CREATED,
    UPDATED,
    WOULD_PRUNE,
    PRUNED,
    TITLE,
    HEADER,
    MUTED,
    TEXT,
)


__all__ = ("ReportedSnapshot", "PrunedSnapshot", "render_session_report")


@dataclass(frozen=True)
class ReportedSnapshot:
    """One snapshot the session wrote, and the target it was written to.

    `nodeid`, `key` and `recorder` are the three facts `ditto list` shows, so a
    snapshot is named the same way wherever it appears.
    """

    target_id: str
    nodeid: str
    key: str
    recorder: str


@dataclass(frozen=True)
class PrunedSnapshot:
    """One snapshot a prune deleted, and the target it was deleted from.

    Carries the storage name rather than a test and key: a snapshot prune
    deletes is one `ditto.lock` does not record, so the lock holds no identity
    for it. The storage name is what finds the file, and the same key can sit
    under two targets, so the target id is part of the record.
    """

    target_id: str
    storage_key: str


_Record = TypeVar("_Record", ReportedSnapshot, PrunedSnapshot)


def _by_target(items: Iterable[_Record]) -> list[tuple[str, list[_Record]]]:
    """Group records by target id, in the order the targets were first used."""
    grouped: dict[str, list[_Record]] = {}
    for item in items:
        grouped.setdefault(item.target_id, []).append(item)
    return list(grouped.items())


def _written_rows(items: Sequence[ReportedSnapshot]) -> Table:
    """One row per written snapshot: the test, its key, and its recorder."""
    rows = Table.grid(padding=(0, 2))
    for _ in range(3):
        rows.add_column(overflow="fold")
    for item in items:
        rows.add_row(
            Text(item.nodeid, overflow="fold"),
            Text(item.key, overflow="fold"),
            Text(item.recorder, overflow="fold"),
        )
    return rows


def _pruned_rows(items: Sequence[PrunedSnapshot]) -> Table:
    """One row per deleted snapshot, named by the storage name it had."""
    rows = Table.grid(padding=(0, 2))
    rows.add_column(overflow="fold")
    for item in items:
        rows.add_row(Text(item.storage_key, overflow="fold"))
    return rows


def _block(
    label: str,
    colour: str,
    items: Sequence[_Record],
    render: Callable[[Sequence[_Record]], RenderableType],
    note: str = "",
) -> list[RenderableType]:
    """A labelled section: the label and its count, then each target's snapshots.

    Every snapshot gets a line of its own under its target, instead of trailing
    the first one across the same line, so a long name wraps without knocking
    the rest out of alignment.
    """
    parts: list[RenderableType] = [
        Text.assemble(
            (f"  {label}  ", f"bold {colour}"),
            (str(len(items)), f"bold {TEXT}"),
        )
    ]
    for target_id, target_items in _by_target(items):
        parts.append(Text(f"    {target_id}", style=f"bold {HEADER}"))
        parts.append(render(target_items))
        if note:
            parts.append(Text(f"    {note}", style=MUTED))
    return parts


def render_session_report(
    created: Sequence[ReportedSnapshot],
    updated: Sequence[ReportedSnapshot],
    pruned: Sequence[PrunedSnapshot],
    would_prune: Sequence[PrunedSnapshot],
    console: Console | None = None,
) -> None:
    """Render the end-of-session ditto snapshot report via Rich.

    Snapshots are grouped under the target they belong to, and each is named by
    the test, key and recorder `ditto list` shows. Silent when there is nothing
    to report.

    Parameters
    ----------
    created : Sequence[ReportedSnapshot]
        Snapshots written for the first time this session.
    updated : Sequence[ReportedSnapshot]
        Existing snapshots overwritten via `--ditto-update`.
    pruned : Sequence[PrunedSnapshot]
        Snapshots deleted via `--ditto-prune`, with the target each was in.
    would_prune : Sequence[PrunedSnapshot]
        Snapshots a `--ditto-prune` run would delete (shown under
        `--ditto-prune-dry-run`), with the target each is in.
    console : Console, optional
        Rich Console to write to. Defaults to stderr.
    """
    if not any([created, updated, pruned, would_prune]):
        return

    if console is None:
        console = Console(stderr=True)

    parts: list[RenderableType] = []
    if created:
        parts += _block("created", CREATED, created, _written_rows)
    if updated:
        parts += _block("updated", UPDATED, updated, _written_rows)
    if pruned:
        parts += _block("pruned", PRUNED, pruned, _pruned_rows)
    if would_prune:
        parts += _block(
            "would prune",
            WOULD_PRUNE,
            would_prune,
            _pruned_rows,
            note="(use --ditto-prune to delete)",
        )

    console.print()
    console.print(
        Panel(
            Group(*parts),
            title=Text("ditto snapshot report", style=f"bold {TITLE}"),
            title_align="left",
            border_style=TITLE,
            expand=False,
        )
    )
