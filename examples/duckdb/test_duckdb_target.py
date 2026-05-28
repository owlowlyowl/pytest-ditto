"""Show a registered duckdb:// backend selected via target=."""

from __future__ import annotations

import os
from pathlib import Path

import ditto


def _default_duckdb_target() -> str:
    database_path = Path(__file__).with_name(".example-snapshots.duckdb").resolve()
    return f"duckdb://{database_path.as_posix()}"


DUCKDB_TARGET = os.getenv("DITTO_DUCKDB_TARGET", _default_duckdb_target())


@ditto.record("json", target=DUCKDB_TARGET)
def test_round_trips_value_when_mark_uses_registered_duckdb_target(snapshot) -> None:
    """A DuckDB target replays the stored payload on later runs."""
    payload = {"answer": 42, "kind": "duckdb"}

    actual = snapshot(payload, key="payload")

    expected = payload
    assert actual == expected
