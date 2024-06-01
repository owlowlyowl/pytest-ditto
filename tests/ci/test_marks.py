import pytest

import ditto


def test_no_mark(snapshot) -> None:
    key = "no-mark"
    snapshot(77, key=key)
    assert snapshot.filepath(key).exists()
    # no mark persistence default is pickle
    assert snapshot.filepath(key).suffix == ".pkl"


@ditto.record("pkl")
def test_raw_mark_pickle(snapshot) -> None:
    key = "raw-mark"
    snapshot(1, key=key)
    assert snapshot.filepath(key).exists()
    assert snapshot.filepath(key).suffix == ".pkl"


@ditto.record("json")
def test_raw_mark_json(snapshot) -> None:
    key = "raw-mark"
    snapshot(1, key=key)
    assert snapshot.filepath(key).exists()
    assert snapshot.filepath(key).suffix == ".json"


@ditto.record("yaml")
def test_raw_mark_yaml(snapshot) -> None:
    key = "raw-mark"
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
def test_static_mark_yaml(snapshot) -> None:
    key = "static-mark"
    snapshot(77, key=key)
    assert snapshot.filepath(key).exists()
    assert snapshot.filepath(key).suffix == ".yaml"


@ditto.json
def test_explicit_mark_json(snapshot) -> None:
    key = "static-mark"
    snapshot(77, key=key)
    assert snapshot.filepath(key).exists()
    assert snapshot.filepath(key).suffix == ".json"


@ditto.pickle
def test_explicit_mark_pickle(snapshot) -> None:
    key = "static-mark"
    snapshot(77, key=key)
    assert snapshot.filepath(key).exists()
    assert snapshot.filepath(key).suffix == ".pkl"
