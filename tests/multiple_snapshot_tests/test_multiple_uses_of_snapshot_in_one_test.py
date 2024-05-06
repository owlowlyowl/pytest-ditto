import pytest

import ditto


# need something like a calling function global cache to identify when calling twice
# within same test - use session config?

# the snapshot class needs to have an internal counter to see how many times it was
# called using the same parameters, so can stop multiple same calls.


@pytest.mark.xfail(
    reason="snapshot used twice, no ids", raises=ditto.snapshot.DittoSecondLoadError
)
@ditto.record("json")
def test_multiple_uses_of_snapshot(snapshot):
    assert 1 == snapshot(1)
    assert 2 == snapshot(2)


@ditto.record("json")
def test_one_none_one_empty_id(snapshot):
    assert 1 == snapshot(1)
    assert 2 == snapshot(2, identifier="b")
