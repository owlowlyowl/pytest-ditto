from __future__ import annotations

import os

import ditto

REDIS_TARGET = os.environ["DITTO_REDIS_TARGET"]


def _payload(name: str) -> dict[str, object]:
    return {
        "backend": "redis",
        "name": name,
        "values": [7, 8, 9],
    }


@ditto.record("json", target=REDIS_TARGET)
def test_alpha(snapshot):
    expected = _payload("alpha")
    assert snapshot(expected, key="alpha") == expected


@ditto.record("json", target=REDIS_TARGET)
def test_beta(snapshot):
    expected = _payload("beta")
    assert snapshot(expected, key="beta") == expected

