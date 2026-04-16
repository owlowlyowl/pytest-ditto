"""Show a project-wide default target from pytest.ini."""

from __future__ import annotations

import ditto


@ditto.record("json")
def test_round_trips_value_when_pytest_ini_sets_default_target(snapshot) -> None:
    """A default target from pytest.ini replays the stored payload on later runs."""
    payload = {"answer": 7, "kind": "local-default"}

    actual = snapshot(payload, key="payload")

    expected = payload
    assert actual == expected
