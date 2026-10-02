from collections.abc import Iterable
from dataclasses import dataclass

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ._lockfile import LOCKFILE_NAME, LockOutcome
from ._theme import (
    CREATED,
    FAILED,
    LOCK,
    UPDATED,
    WOULD_PRUNE,
    PRUNED,
    TITLE,
    MUTED,
)
from .snapshot import SnapshotKey


__all__ = ("PrunedSnapshot", "render_session_report")

# Wide enough for the longest row label, "not written".
_LABEL_WIDTH = 13


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
    text.append(f"  {label:<{_LABEL_WIDTH}}", style=f"bold {colour}")
    text.append(f"{len(items):<5}", style=colour)
    if items:
        first = items[0].display_name if isinstance(items[0], SnapshotKey) else items[0]
        text.append(first, style=colour)
        if suffix:
            text.append(f"  {suffix}", style=MUTED)
        for item in items[1:]:
            name = item.display_name if isinstance(item, SnapshotKey) else item
            text.append(f"\n  {'':<{_LABEL_WIDTH + 5}}{name}", style=colour)
    return text


def _pruned_block(
    items: list[PrunedSnapshot],
    colour: str,
    label: str,
    suffix: str = "",
) -> Text:
    """One labelled row naming each pruned snapshot's target above its keys."""
    text = Text()
    text.append(f"  {label:<{_LABEL_WIDTH}}", style=f"bold {colour}")
    text.append(f"{len(items):<5}", style=colour)
    for target_id, keys in _pruned_by_target(items):
        text.append(f"\n  {'':<{_LABEL_WIDTH + 5}}{target_id}", style=f"bold {colour}")
        if suffix:
            text.append(f"  {suffix}", style=MUTED)
        for key in keys:
            text.append(f"\n  {'':<{_LABEL_WIDTH + 9}}{key}", style=colour)
    return text


def _lock_delta(lock: LockOutcome) -> str:
    """The entries a written lock gained and lost, or that they're unknown."""
    if lock.added is None or lock.removed is None:
        return "previous entries unknown"
    return f"{lock.added} added, {lock.removed} removed"


def _lock_block(lock: LockOutcome) -> Text:
    """The row saying what the session did to `ditto.lock`."""
    colour = LOCK if lock.status == "written" else FAILED
    text = Text()
    text.append(f"  {'lock':<{_LABEL_WIDTH}}", style=f"bold {colour}")
    text.append(f"{LOCKFILE_NAME} {lock.status}", style=colour)
    if lock.status == "written":
        text.append(f"  {_lock_delta(lock)}", style=MUTED)
    return text


def render_session_report(
    created: list[SnapshotKey],
    updated: list[SnapshotKey],
    pruned: list[PrunedSnapshot],
    would_prune: list[PrunedSnapshot],
    write_failed: list[SnapshotKey] | None = None,
    prune_failed: list[PrunedSnapshot] | None = None,
    lock: LockOutcome | None = None,
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
    write_failed : list[SnapshotKey], optional
        Snapshots whose write to the backend raised.
    prune_failed : list[PrunedSnapshot], optional
        Snapshots `--ditto-prune` tried and failed to delete.
    lock : LockOutcome, optional
        What the session did to `ditto.lock`; an unchanged lock isn't shown.
    console : Console, optional
        Rich Console to write to. Defaults to stderr.
    """
    write_failed = write_failed or []
    prune_failed = prune_failed or []
    lock = lock or LockOutcome()
    lock_changed = lock.status != "unchanged"
    snapshot_rows = [created, updated, write_failed, pruned, prune_failed, would_prune]
    if not any(snapshot_rows) and not lock_changed:
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
    if write_failed:
        lines.append(_label_block(write_failed, FAILED, "not written"))
    if pruned:
        lines.append(_pruned_block(pruned, PRUNED, "pruned"))
    if prune_failed:
        lines.append(_pruned_block(prune_failed, FAILED, "not pruned"))
    if would_prune:
        lines.append(
            _pruned_block(
                would_prune,
                WOULD_PRUNE,
                "would prune",
                suffix="(use --ditto-prune to delete)",
            )
        )
    if lock_changed:
        lines.append(_lock_block(lock))

    body = Text("\n").join(lines)
    panel = Panel(
        body,
        title=f"[bold {TITLE}]ditto snapshot report[/bold {TITLE}]",
        border_style=TITLE,
        expand=False,
    )
    console.print(panel)
