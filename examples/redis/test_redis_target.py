"""Show a registered redis:// backend selected via target=."""

from __future__ import annotations

import os

import ditto


REDIS_TARGET = os.getenv("DITTO_REDIS_TARGET", "redis://localhost:6380/0")


@ditto.record("json", target=REDIS_TARGET)
def test_round_trips_value_when_mark_uses_registered_redis_target(snapshot) -> None:
    """A Redis target replays the stored payload on later runs."""
    payload = {"answer": 42, "kind": "redis"}

    actual = snapshot(payload, key="payload")

    expected = payload
    assert actual == expected
