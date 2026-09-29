"""Snapshots written by pytest-ditto 1.x load unchanged.

The committed snapshot for this module was written by pytest-ditto 1.1.0's
default (pickle) recorder, from the value `expected_value()` returns:

    def test_value(snapshot):
        assert snapshot(value(), key="value") == value()

1.x stored it as `.ditto/test_value@value.pkl`. 2.0 names the file after the
module, test, key and a hash of them, ending with the recorder's name, so the
file was renamed to its 2.0 name, ending `.pickle`; its bytes are unchanged.
"""

import datetime
import hashlib
from decimal import Decimal
from pathlib import Path

import ditto

SNAPSHOT = (
    Path(__file__).parent
    / ".ditto"
    / (
        "tests.ci.test_legacy.test_loads_a_snapshot_written_by_pytest_ditto_1x"
        "@value~30588965.pickle"
    )
)
SNAPSHOT_SHA256 = "503b118f791d9d8dfac3d509acb38e77230223ffa1517b57a87c184d1411146b"


def expected_value() -> dict[str, object]:
    return {
        "set": {1, 2, 3},
        "tuple": (1, "a"),
        "bytes": b"\x00\x01",
        "complex": 1 + 2j,
        "date": datetime.date(2024, 1, 2),
        "decimal": Decimal("1.10"),
    }


def test_the_committed_snapshot_is_the_file_1x_wrote() -> None:
    """The snapshot is byte-for-byte the file pytest-ditto 1.1.0 wrote."""
    actual = hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest()

    expected = SNAPSHOT_SHA256
    assert actual == expected


@ditto.pickle
def test_loads_a_snapshot_written_by_pytest_ditto_1x(snapshot) -> None:
    """The pickle recorder reads a 1.x snapshot and returns the value 1.x saved.

    The data passed in is a placeholder, so the test only passes if the value
    comes from the stored file.
    """
    actual = snapshot(None, key="value")

    expected = expected_value()
    assert actual == expected
