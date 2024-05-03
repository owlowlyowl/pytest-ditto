from pathlib import Path

import pytest

import ditto
from ditto.io import PickleIO, JsonIO
from ditto.snapshot import Snapshot


def get_data(value: int) -> int:
    return value


def func(value: int) -> int:
    return value + 34


@ditto.record("yaml")
def test_cache_input_data(snapshot) -> None:
    data = snapshot(get_data(1))
    assert func(data) == 2


@pytest.fixture(scope="function")
def data(snapshot) -> int:
    return snapshot(get_data(1), identifier="data")

# def data() -> int:
#     snap = Snapshot(
#         path=Path(__file__).parent / ".ditto",
#         name="data",
#         record=True,
#         io=JsonIO(),
#     )
#     return snap(get_data(1))


@ditto.record("yaml")
def test_this(snapshot, data) -> None:
    result = func(data)
    assert result == snapshot(result)


@ditto.record("yaml")
def test_use_cached_input_data_and_snapshot_result(snapshot, data) -> None:
# def test_use_cached_input_data_and_snapshot_result(snapshot) -> None:
#     value = data()
    value = data
    result = func(value)
    assert result == snapshot(result)


def test_neq():
    assert 1 == 2