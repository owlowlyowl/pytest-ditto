from ditto import Snapshot


def test_snapshot_fixture_exists(snapshot):
    assert isinstance(snapshot, Snapshot)


def test_snapshot_record(snapshot):
    snapshot(77, key="b")


def test_snapshot_twice(snapshot):
    snapshot(77, key="a")
    snapshot("(>'.')>", key="b")
