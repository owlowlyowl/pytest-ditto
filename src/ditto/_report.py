from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
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
    HEADER,
    MUTED,
    TEXT,
)
from .snapshot import SnapshotKey, SnapshotWrite


__all__ = ("PrunedSnapshot", "render_session_report")

# Wide enough for the longest row label, "would prune".
_LABEL_WIDTH = 13

# How each write outcome is labelled, in the order the summary counts them.
_WRITE_LABELS: Mapping[str, tuple[str, str]] = {
    "created": ("created", CREATED),
    "rewritten": ("rewritten", UPDATED),
    "write_failed": ("not written", FAILED),
}
_WRITE_LABEL_WIDTH = max(len(label) for label, _ in _WRITE_LABELS.values())


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


def _file_and_test(key: SnapshotKey) -> tuple[str, str]:
    """The test file and the test in it, from the node id when there is one.

    A `Snapshot` built outside the fixture has no node id, so its key's module
    and group name stand in.
    """
    if not key.nodeid:
        return key.module, key.group_name
    file, _, test = key.nodeid.partition("::")
    return file, test


def _by_file_and_test(
    writes: Iterable[SnapshotWrite],
) -> dict[str, dict[str, list[SnapshotWrite]]]:
    """Group writes by test file, then test, each in the order first written."""
    grouped: dict[str, dict[str, list[SnapshotWrite]]] = {}
    for write in writes:
        file, test = _file_and_test(write.key)
        grouped.setdefault(file, {}).setdefault(test, []).append(write)
    return grouped


def _write_counts(writes: Sequence[SnapshotWrite]) -> Text:
    """One line counting each write outcome: '2 created · 1 rewritten'."""
    counts = Counter(write.outcome for write in writes)
    parts = [
        (f"{counts[outcome]} {label}", f"bold {colour}")
        for outcome, (label, colour) in _WRITE_LABELS.items()
        if counts[outcome]
    ]
    text = Text()
    for i, part in enumerate(parts):
        if i:
            text.append(" · ", style=MUTED)
        text.append(*part)
    return text


def _write_row(write: SnapshotWrite, key_width: int) -> Text:
    """One write: its outcome, then the snapshot's key and recorder."""
    label, colour = _WRITE_LABELS[write.outcome]
    return Text.assemble(
        "    ",
        (f"{label:<{_WRITE_LABEL_WIDTH}}", f"bold {colour}"),
        "  ",
        (f"{write.key.key:<{key_width}}", TEXT),
        "  ",
        (write.key.identifier, MUTED),
    )


def _writes_block(writes: Sequence[SnapshotWrite]) -> Text:
    """The counts, then every write grouped under its test file and test.

    Each snapshot is named by its key and recorder under its test, the
    identity `ditto.lock` and `ditto list` use, rather than a storage name.
    """
    lines = [_write_counts(writes)]
    for file, tests in _by_file_and_test(writes).items():
        lines.append(Text())
        lines.append(Text(file, style=f"bold {HEADER}"))
        for test, test_writes in tests.items():
            lines.append(Text(f"  {test}", style=TEXT))
            key_width = max(len(write.key.key) for write in test_writes)
            lines.extend(_write_row(write, key_width) for write in test_writes)
    return Text("\n").join(lines)


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
    elif lock.reason:
        text.append(f"  {lock.reason}", style=MUTED)
    return text


def render_session_report(
    writes: Sequence[SnapshotWrite] = (),
    pruned: Sequence[PrunedSnapshot] = (),
    would_prune: Sequence[PrunedSnapshot] = (),
    prune_failed: Sequence[PrunedSnapshot] = (),
    lock: LockOutcome | None = None,
    console: Console | None = None,
) -> None:
    """Render the end-of-session ditto snapshot report via Rich.

    Silent when there is nothing to report.

    Parameters
    ----------
    writes : Sequence[SnapshotWrite]
        Every snapshot write this session, created, rewritten or failed.
    pruned : Sequence[PrunedSnapshot]
        Snapshots deleted via `--ditto-prune`, with the target each was in.
    would_prune : Sequence[PrunedSnapshot]
        Snapshots a `--ditto-prune` run would delete (shown under
        `--ditto-prune-dry-run`), with the target each is in.
    prune_failed : Sequence[PrunedSnapshot]
        Snapshots `--ditto-prune` tried and failed to delete.
    lock : LockOutcome, optional
        What the session did to `ditto.lock`; an unchanged lock isn't shown.
    console : Console, optional
        Rich Console to write to. Defaults to stderr.
    """
    lock = lock or LockOutcome()
    lock_changed = lock.status != "unchanged"
    if not any((writes, pruned, prune_failed, would_prune)) and not lock_changed:
        return

    if console is None:
        console = Console(stderr=True)

    console.print()
    console.print()

    rows: list[Text] = []
    if pruned:
        rows.append(_pruned_block(list(pruned), PRUNED, "pruned"))
    if prune_failed:
        rows.append(_pruned_block(list(prune_failed), FAILED, "not pruned"))
    if would_prune:
        rows.append(
            _pruned_block(
                list(would_prune),
                WOULD_PRUNE,
                "would prune",
                suffix="(use --ditto-prune to delete)",
            )
        )
    if lock_changed:
        rows.append(_lock_block(lock))

    sections = [_writes_block(writes)] if writes else []
    if rows:
        sections.append(Text("\n").join(rows))

    body = Text("\n\n").join(sections)
    panel = Panel(
        body,
        title=f"[bold {TITLE}]ditto snapshot report[/bold {TITLE}]",
        border_style=TITLE,
        expand=False,
    )
    console.print(panel)
