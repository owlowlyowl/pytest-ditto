from collections.abc import Iterable
from dataclasses import dataclass

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ._theme import (
    CREATED,
    UPDATED,
    WOULD_PRUNE,
    PRUNED,
    TITLE,
    MUTED,
)
from .snapshot import SnapshotKey


__all__ = ("PrunedSnapshot", "render_session_report")


@dataclass(frozen=True)
class PrunedSnapshot:
    """One snapshot a prune deleted, and the target it was deleted from.

    Two targets can hold the same storage key, so a bare key doesn't say which
    backend it came from.
    """

    target_id: str
    key: str


def _pruned_by_target(
    items: Iterable[PrunedSnapshot],
) -> list[tuple[str, list[str]]]:
    """Group pruned storage keys by target id, targets in first-seen order."""
    keys: dict[str, list[str]] = {}
    for item in items:
        keys.setdefault(item.target_id, []).append(item.key)
    return [(target_id, sorted(target_keys)) for target_id, target_keys in keys.items()]


def _label_block(
    items: list[SnapshotKey] | list[str],
    colour: str,
    label: str,
    suffix: str = "",
) -> Text:
    """One labelled row (wrapping to additional lines) for the report panel."""
    text = Text()
    text.append(f"  {label:<10}", style=f"bold {colour}")
    text.append(f"{len(items):<5}", style=colour)
    if items:
        first = items[0].display_name if isinstance(items[0], SnapshotKey) else items[0]
        text.append(first, style=colour)
        if suffix:
            text.append(f"  {suffix}", style=MUTED)
        for item in items[1:]:
            name = item.display_name if isinstance(item, SnapshotKey) else item
            text.append(f"\n  {'':<15}{name}", style=colour)
    return text


def _pruned_block(
    items: list[PrunedSnapshot],
    colour: str,
    label: str,
    suffix: str = "",
) -> Text:
    """One labelled row naming each pruned snapshot's target above its keys."""
    text = Text()
    text.append(f"  {label:<10}", style=f"bold {colour}")
    text.append(f"{len(items):<5}", style=colour)
    for target_id, keys in _pruned_by_target(items):
        text.append(f"\n  {'':<15}{target_id}", style=f"bold {colour}")
        if suffix:
            text.append(f"  {suffix}", style=MUTED)
        for key in keys:
            text.append(f"\n  {'':<19}{key}", style=colour)
    return text


def render_session_report(
    created: list[SnapshotKey],
    updated: list[SnapshotKey],
    pruned: list[PrunedSnapshot],
    would_prune: list[PrunedSnapshot],
    console: Console | None = None,
) -> None:
    """Render the end-of-session ditto snapshot report via Rich.

    Silent when there is nothing to report.

    Parameters
    ----------
    created : list[SnapshotKey]
        Snapshots written for the first time this session.
    updated : list[SnapshotKey]
        Existing snapshots overwritten via `--ditto-update`.
    pruned : list[PrunedSnapshot]
        Snapshots deleted via `--ditto-prune`, with the target each was in.
    would_prune : list[PrunedSnapshot]
        Snapshots a `--ditto-prune` run would delete (shown under
        `--ditto-prune-dry-run`), with the target each is in.
    console : Console, optional
        Rich Console to write to. Defaults to stderr.
    """
    if not any([created, updated, pruned, would_prune]):
        return

    if console is None:
        console = Console(stderr=True)

    console.print()
    console.print()

    lines: list[Text] = []

    if created:
        lines.append(_label_block(created, CREATED, "created"))
    if updated:
        lines.append(_label_block(updated, UPDATED, "updated"))
    if pruned:
        lines.append(_pruned_block(pruned, PRUNED, "pruned"))
    if would_prune:
        lines.append(
            _pruned_block(
                would_prune,
                WOULD_PRUNE,
                "would prune",
                suffix="(use --ditto-prune to delete)",
            )
        )

    body = Text("\n").join(lines)
    panel = Panel(
        body,
        title=f"[bold {TITLE}]ditto snapshot report[/bold {TITLE}]",
        border_style=TITLE,
        expand=False,
    )
    console.print(panel)
