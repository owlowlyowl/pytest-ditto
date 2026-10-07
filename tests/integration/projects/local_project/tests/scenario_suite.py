from __future__ import annotations

import ditto


def _payload(name: str) -> dict[str, object]:
    return {
        "backend": "local",
        "name": name,
        "values": [1, 2, 3],
    }


@ditto.record("json")
def test_alpha(snapshot):
    expected = _payload("alpha")
    assert snapshot(expected, key="alpha") == expected


@ditto.record("json")
def test_beta(snapshot):
    expected = _payload("beta")
    assert snapshot(expected, key="beta") == expected
