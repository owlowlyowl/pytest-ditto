"""How verify and prune name the target each drifted key is in (#185)."""

from io import StringIO

from rich.console import Console

from ditto._lockfile import (
    LOCKFILE_VERSION,
    LockEntry,
    LockFile,
    LockTarget,
)
from ditto._report import PrunedSnapshot, render_session_report
from ditto.plugin._drift import TargetDrift, _drift_lines, _target_identities


def _identities() -> dict[str, LockEntry]:
    """The lock identities a drifted `.ditto` key is looked up in."""
    entry = LockEntry(
        nodeid="tests/test_a.py::test_numbers[1]", key="value", recorder="json"
    )
    lock = LockFile(
        version=LOCKFILE_VERSION,
        targets={".ditto": LockTarget(scheme="file", entries=(entry,))},
    )
    return _target_identities(lock, ".ditto", "file")


def test_names_a_missing_key_by_the_test_the_lock_records_it_for() -> None:
    """A missing key the lock knows is shown as node id, key and storage name."""
    missing = "tests.test_a.test_numbers[1]@value~e51845259fe080be.json"
    drift = TargetDrift(".ditto", "file", [missing], [], [])

    actual = _drift_lines(drift, _identities())

    expected = [
        "  .ditto:",
        "    missing (recorded in lock, absent from backend):",
        "      tests/test_a.py::test_numbers[1]  value  "
        "tests.test_a.test_numbers[1]@value~e51845259fe080be.json",
    ]
    assert actual == expected


def test_names_an_orphan_by_its_storage_name_alone() -> None:
    """An orphan has no lock entry, so its storage name is all there is to say."""
    orphan = "tests.test_x@k~0123456789abcdef.json"
    drift = TargetDrift(".ditto", "file", [], [orphan], [])

    actual = _drift_lines(drift, _identities())

    assert actual == [
        "  .ditto:",
        "    orphan (in backend, not in lock):",
        "      tests.test_x@k~0123456789abcdef.json",
    ]


def test_omits_a_drift_kind_the_target_has_none_of() -> None:
    """Only the kinds with keys get a heading, so an empty one can't be misread."""
    drift = TargetDrift(
        ".ditto", "file", [], [], ["tests.test_y@k~0123456789abcdef.json"]
    )

    actual = _drift_lines(drift, _identities())

    assert actual == [
        "  .ditto:",
        "    unsynced (produced this run, not in lock; run `ditto lock`):",
        "      tests.test_y@k~0123456789abcdef.json",
    ]


def test_returns_no_identities_for_a_target_the_lock_does_not_record() -> None:
    """A target missing from the lock has no keys to name by test."""
    lock = LockFile(
        version=LOCKFILE_VERSION,
        targets={".ditto": LockTarget(scheme="file", entries=())},
    )

    assert _target_identities(lock, "s3://bucket/other", "s3") == {}


def test_report_groups_pruned_keys_under_the_target_they_came_from() -> None:
    """The same key pruned from two targets reads as two different snapshots."""
    stream = StringIO()
    shared_key = "tests.test_a@a~0123456789abcdef.json"

    render_session_report(
        created=[],
        updated=[],
        pruned=[
            PrunedSnapshot(".ditto", shared_key),
            PrunedSnapshot("s3://b/d", shared_key),
        ],
        would_prune=[],
        console=Console(file=stream, width=100),
    )

    assert ".ditto" in stream.getvalue()
    assert "s3://b/d" in stream.getvalue()


def test_report_names_each_target_above_its_own_pruned_keys() -> None:
    """A key is listed under its own target, not whichever came first."""
    stream = StringIO()

    render_session_report(
        created=[],
        updated=[],
        pruned=[
            PrunedSnapshot("s3://b/d", "second@k~1111111111111111.json"),
            PrunedSnapshot(".ditto", "first@k~2222222222222222.json"),
        ],
        would_prune=[],
        console=Console(file=stream, width=100),
    )
    output = stream.getvalue()

    assert output.index("s3://b/d") < output.index("second@k")
    assert output.index(".ditto") < output.index("first@k")
