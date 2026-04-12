"""Show an explicit local file target beside the test file."""

from __future__ import annotations

import ditto


@ditto.record("json", target="file://.example-snaps")
def test_round_trips_value_when_mark_uses_explicit_file_target(snapshot) -> None:
    """An explicit file target replays the stored payload on later runs."""
    payload = {"answer": 42, "kind": "local-explicit"}

    actual = snapshot(payload, key="payload")

    expected = payload
    assert actual == expected
