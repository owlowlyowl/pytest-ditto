from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ._theme import (
    CREATED,
    UPDATED,
    UNUSED,
    PRUNED,
    TITLE,
    MUTED,
)
from .snapshot import SnapshotKey


__all__ = ("render_session_report",)


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


def render_session_report(
    created: list[SnapshotKey],
    updated: list[SnapshotKey],
    pruned: list[str],
    unused: list[str],
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
    pruned : list[str]
        Raw backend keys deleted via `--ditto-prune`.
    unused : list[str]
        Raw backend keys on disk not accessed this session.
    console : Console, optional
        Rich Console to write to. Defaults to stderr.
    """
    if not any([created, updated, pruned, unused]):
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
        lines.append(_label_block(pruned, PRUNED, "pruned"))
    if unused:
        lines.append(
            _label_block(unused, UNUSED, "unused", suffix="(use --ditto-prune)")
        )

    body = Text("\n").join(lines)
    panel = Panel(
        body,
        title=f"[bold {TITLE}]ditto snapshot report[/bold {TITLE}]",
        border_style=TITLE,
        expand=False,
    )
    console.print(panel)
