def test_snapshot_fixture_without_use_of_decorator_mark(snapshot):
    assert 77 == snapshot(77)


def test_snapshot_with_integer_identifier(snapshot):
    assert 77 == snapshot(77, identifier=1029384756)
