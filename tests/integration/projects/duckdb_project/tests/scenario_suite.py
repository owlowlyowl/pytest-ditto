from __future__ import annotations

import os

import ditto

DUCKDB_TARGET = os.environ["DITTO_DUCKDB_TARGET"]


def _payload(name: str) -> dict[str, object]:
    return {
        "backend": "duckdb",
        "name": name,
        "values": [4, 5, 6],
    }


@ditto.record("json", target=DUCKDB_TARGET)
def test_alpha(snapshot):
    expected = _payload("alpha")
    assert snapshot(expected, key="alpha") == expected


@ditto.record("json", target=DUCKDB_TARGET)
def test_beta(snapshot):
    expected = _payload("beta")
    assert snapshot(expected, key="beta") == expected

