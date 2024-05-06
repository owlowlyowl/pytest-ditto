from ditto import Snapshot


def test_snapshot_fixture_exists(snapshot):
    assert isinstance(snapshot, Snapshot)


def test_snapshot_record(snapshot):
    snapshot(77)


def test_snapshot_twice(snapshot):
    snapshot(77, identifier="a")
    snapshot("(>'.')>", identifier="b")
