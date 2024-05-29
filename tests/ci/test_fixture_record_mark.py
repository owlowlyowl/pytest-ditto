import pytest

import ditto
import ditto.exceptions
import ditto.marks


@ditto.record("pkl")
def test_pickle(snapshot) -> None:
    key = "abc"
    snapshot(1, key=key)
    assert snapshot.filepath(key).exists()
    assert snapshot.filepath(key).suffix == ".pkl"


@ditto.record("json")
def test_json(snapshot) -> None:
    key = "abc"
    snapshot(1, key=key)
    assert snapshot.filepath(key).exists()
    assert snapshot.filepath(key).suffix == ".json"


@ditto.record("yaml")
def test_yaml(snapshot) -> None:
    key = "abc"
    snapshot(1, key=key)
    assert snapshot.filepath(key).exists()
    assert snapshot.filepath(key).suffix == ".yaml"


@pytest.mark.xfail(
    reason="multiple record markers", raises=ditto.exceptions.AdditionalMarkError
)
@ditto.record("pkl")
@ditto.record("json")
def test_only_one_record_mark_allowed(snapshot) -> None:
    snapshot(1, key="a")


@ditto.yaml
def test_explicit_mark_yaml(snapshot) -> None:
    key = "xyz"
    snapshot(77, key=key)
    assert snapshot.filepath(key).exists()
    assert snapshot.filepath(key).suffix == ".yaml"
