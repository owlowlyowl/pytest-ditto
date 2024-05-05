import pytest


def test_snapshot_fixture_without_use_of_decorator_mark(snapshot):
    snapshot("dummy value")
    assert snapshot.filepath().exists()


def test_snapshot_with_integer_identifier(snapshot):
    assert 77 == snapshot(77, identifier=1029384756)
