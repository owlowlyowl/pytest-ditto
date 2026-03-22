from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ._theme import (
    CREATED, UPDATED, UNUSED, PRUNED,
    TITLE, MUTED,
)


__all__ = ("render_session_report",)


def _label_block(paths: list[Path], colour: str, label: str, suffix: str = "") -> Text:
    """One labelled row (wrapping to additional lines) for the report panel."""
    text = Text()
    text.append(f"  {label:<10}", style=f"bold {colour}")
    text.append(f"{len(paths):<5}", style=colour)
    if paths:
        text.append(paths[0].name, style=colour)
        if suffix:
            text.append(f"  {suffix}", style=MUTED)
        for p in paths[1:]:
            text.append(f"\n  {'':<15}{p.name}", style=colour)
    return text


def render_session_report(
    created: list[Path],
    updated: list[Path],
    pruned: list[Path],
    unused: list[Path],
    console: Console | None = None,
) -> None:
    """
    Render the end-of-session ditto snapshot report via Rich.

    Silent when there is nothing to report.

    Parameters
    ----------
    created : list[Path]
        Snapshot files written for the first time this session.
    updated : list[Path]
        Existing snapshot files overwritten via `--ditto-update`.
    pruned : list[Path]
        Snapshot files deleted via `--ditto-prune`.
    unused : list[Path]
        Snapshot files on disk that were not accessed this session.
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
        lines.append(_label_block(unused, UNUSED, "unused", suffix="(use --ditto-prune)"))

    body = Text("\n").join(lines)
    panel = Panel(
        body,
        title=f"[bold {TITLE}]ditto snapshot report[/bold {TITLE}]",
        border_style=TITLE,
        expand=False,
    )
    console.print(panel)
