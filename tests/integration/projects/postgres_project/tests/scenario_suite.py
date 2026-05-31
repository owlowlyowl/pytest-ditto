from __future__ import annotations

import os

import ditto

POSTGRES_TARGET = os.environ["DITTO_POSTGRES_TARGET"]


def _payload(name: str) -> dict[str, object]:
    return {
        "backend": "postgresql",
        "name": name,
        "values": [10, 11, 12],
    }


@ditto.record("json", target=POSTGRES_TARGET)
def test_alpha(snapshot):
    expected = _payload("alpha")
    assert snapshot(expected, key="alpha") == expected


@ditto.record("json", target=POSTGRES_TARGET)
def test_beta(snapshot):
    expected = _payload("beta")
    assert snapshot(expected, key="beta") == expected
