"""Snapshot statistics aggregated from inventory entries."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import NamedTuple

from .._manifest import LocatedEntry
from ._data import RecorderInfo, _human_size, _parse_snapshot_name, _recorder_name


@dataclass(frozen=True)
class SizeSummary:
    known_bytes: int = 0
    unknown_count: int = 0


@dataclass(frozen=True)
class RecorderStats:
    count: int
    size: SizeSummary


class ExtremeSnapshot(NamedTuple):
    """The snapshot with the oldest or newest timestamp, and where it lives.

    `location` is needed to name it: the same storage key can sit under two
    targets, and the lock records a different test for each.
    """

    modified: float
    storage_key: str
    location: str


@dataclass(frozen=True)
class SnapshotStats:
    total_count: int
    total_size: SizeSummary
    by_recorder: Mapping[str, RecorderStats]
    oldest: ExtremeSnapshot | None
    newest: ExtremeSnapshot | None


def _add_size(summary: SizeSummary, size_bytes: int | None) -> SizeSummary:
    """Return `summary` with one known or unknown snapshot size added."""
    if size_bytes is None:
        return SizeSummary(summary.known_bytes, summary.unknown_count + 1)
    return SizeSummary(summary.known_bytes + size_bytes, summary.unknown_count)


def _sum_sizes(summaries: Iterable[SizeSummary]) -> SizeSummary:
    """Combine size summaries without discarding unknown-size counts."""
    known_bytes = 0
    unknown_count = 0
    for summary in summaries:
        known_bytes += summary.known_bytes
        unknown_count += summary.unknown_count
    return SizeSummary(known_bytes=known_bytes, unknown_count=unknown_count)


def _format_size_summary(summary: SizeSummary) -> str:
    """Render a complete, partial, or entirely unknown size total."""
    if summary.unknown_count == 0:
        return _human_size(summary.known_bytes)
    if summary.known_bytes == 0:
        return "—"
    return f"{_human_size(summary.known_bytes)} known"


def gather_stats(
    entries: Sequence[LocatedEntry], ext_map: Mapping[str, RecorderInfo]
) -> SnapshotStats:
    """Aggregate snapshot statistics from inventory entries, each with its target."""
    total_size = SizeSummary()
    by_recorder: dict[str, RecorderStats] = {}
    oldest: ExtremeSnapshot | None = None
    newest: ExtremeSnapshot | None = None

    for located in entries:
        entry = located.entry
        total_size = _add_size(total_size, entry.size_bytes)
        _, _, ext = _parse_snapshot_name(entry.storage_key)
        recorder_name = _recorder_name(ext, ext_map)
        current = by_recorder.get(
            recorder_name,
            RecorderStats(count=0, size=SizeSummary()),
        )
        by_recorder[recorder_name] = RecorderStats(
            count=current.count + 1,
            size=_add_size(current.size, entry.size_bytes),
        )

        if entry.modified is not None:
            extreme = ExtremeSnapshot(
                entry.modified, entry.storage_key, located.location
            )
            if oldest is None or entry.modified < oldest.modified:
                oldest = extreme
            if newest is None or entry.modified > newest.modified:
                newest = extreme

    return SnapshotStats(
        total_count=len(entries),
        total_size=total_size,
        by_recorder=by_recorder,
        oldest=oldest,
        newest=newest,
    )
