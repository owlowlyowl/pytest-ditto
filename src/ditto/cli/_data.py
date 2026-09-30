"""Snapshot labels, recorder metadata, and size formatting."""

from __future__ import annotations

import importlib.metadata
import re
from collections.abc import Mapping
from dataclasses import dataclass

from ditto.recorders._contract import NAME_PATTERN

_SNAPSHOT_NAME = re.compile(
    r"(?P<test>.+)@(?P<key>[^@~]*)~[0-9a-f]{16}\.(?P<recorder>.+)"
)


def _parse_snapshot_name(filename: str) -> tuple[str, str, str]:
    """Parse a snapshot name into (test label, key label, ext).

    The test label keeps the module prefix (e.g. `tests.test_api.test_get[12_00]`).
    Labels shorten and replace characters of the real test name and key, so
    they are for display when the lock has no entry for the name. Returns ext
    with a leading dot (e.g. `.pandas.parquet`), or `("name", "", "")` for a
    name not in this form.
    """
    match = _SNAPSHOT_NAME.fullmatch(filename)
    if match is None:
        return filename, "", ""
    return match["test"], match["key"], f".{match['recorder']}"


@dataclass(frozen=True)
class RecorderInfo:
    name: str  # e.g. "pandas.parquet"
    identifier: str  # e.g. ".pandas.parquet"
    package: str  # e.g. "pytest-ditto-pandas"


def _load_recorder_infos() -> list[RecorderInfo]:
    """Read every registered recorder from entry-point metadata, importing none.

    A recorder's identifier is its entry-point name.
    """
    return [
        RecorderInfo(
            name=ep.name,
            identifier=f".{ep.name}",
            package=ep.dist.name if ep.dist else "unknown",
        )
        for ep in importlib.metadata.entry_points(group="ditto_recorders")
    ]


def _ext_map(infos: list[RecorderInfo]) -> dict[str, RecorderInfo]:
    """Pure: derive identifier → RecorderInfo lookup from a list of infos."""
    return {info.identifier: info for info in infos}


def _recorder_name(ext: str, ext_map: Mapping[str, RecorderInfo]) -> str:
    """Map a parsed identifier to its recorder name, falling back to the bare one."""
    if ext in ext_map:
        return ext_map[ext].name
    return ext.lstrip(".")


def _human_size(n: int | None) -> str:
    if n is None:
        return "—"
    value: float = n
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{n} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def _mark_for(name: str) -> str:
    """Return the mark a recorder name derives, or "-" for an invalid name."""
    return f"@ditto.{name}" if NAME_PATTERN.fullmatch(name) else "-"
