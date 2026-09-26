import datetime
from decimal import Decimal

import ditto


def make_value() -> dict[str, object]:
    return {
        "set": {1, 2},
        "tuple": (1, 2.5),
        "bytes": b"ditto",
        "date": datetime.date(2026, 9, 27),
        "decimal": Decimal("3.14"),
    }


@ditto.pickle
def test_pickle_snapshot_matches_the_recorded_value(snapshot) -> None:
    """A value snapshotted with pickle equals the recorded snapshot."""
    value = make_value()

    actual = snapshot(value, "value")

    assert actual == value


@ditto.record("pickle")
def test_record_mark_selects_pickle_by_name(snapshot) -> None:
    """`ditto.record("pickle")` selects the same recorder as `ditto.pickle`."""
    value = make_value()

    actual = snapshot(value, "value")

    assert actual == value
