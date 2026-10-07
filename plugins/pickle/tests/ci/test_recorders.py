"""The pickle recorder, as registered through the 2.0 plugin contract."""

import datetime
from decimal import Decimal

import pytest

import ditto
from ditto import recorders


def test_registers_the_recorder_as_pickle() -> None:
    """The recorder is discoverable by the name `pickle`."""
    assert "pickle" in recorders.RECORDER_REGISTRY


def test_registration_keeps_the_plugin_contract() -> None:
    """No contract problem involves the pickle recorder."""
    affected = {n for p in recorders.RECORDER_REGISTRY.problems for n in p.names}

    assert "pickle" not in affected


def test_derives_a_bare_mark() -> None:
    """`ditto.pickle` is the mark for `record("pickle")`."""
    actual = ditto.pickle

    expected = pytest.mark.record("pickle")
    assert actual == expected


@ditto.pickle
def test_mark_selects_the_pickle_recorder(snapshot) -> None:
    """The mark gives the snapshot fixture the pickle recorder, named `pickle`
    in snapshot filenames."""
    actual = snapshot.recorder

    assert actual is recorders.get("pickle")
    assert snapshot.recorder_name == "pickle"


@pytest.mark.parametrize(
    "value",
    [
        pytest.param({1, 2, 3}, id="set"),
        pytest.param((1, "a"), id="tuple"),
        pytest.param(b"\x00\x01", id="bytes"),
        pytest.param(1 + 2j, id="complex"),
        pytest.param(datetime.date(2024, 1, 2), id="date"),
        pytest.param(Decimal("1.10"), id="decimal"),
    ],
)
def test_round_trips_values_json_cannot(value: object) -> None:
    """Values strict JSON rejects or changes load back unchanged."""
    recorder = recorders.get("pickle")
    actual = recorder.loads(recorder.dumps(value))

    assert actual == value
    assert type(actual) is type(value)
