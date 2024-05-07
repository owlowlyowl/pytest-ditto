import pandas as pd
import pytest

import ditto
import ditto.exceptions


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


@ditto.record("pandas_parquet")
def test_pandas_parquet(snapshot) -> None:
    key = "abc"
    snapshot(pd.DataFrame({"a": [1, 2], "b": [3, 4]}), key=key)
    assert snapshot.filepath(key).exists()
    assert snapshot.filepath(key).suffix == ".parquet"


@pytest.mark.xfail(
    reason="multiple record markers", raises=ditto.exceptions.AdditionalMarkError
)
@ditto.record("pkl")
@ditto.record("json")
def test_only_one_record_mark_allowed(snapshot) -> None:
    snapshot(1, key="a")
