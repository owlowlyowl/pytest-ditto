import pytest

import ditto


def get_data(value: int) -> int:
    return value


def func(value: int) -> int:
    return value + 2


@ditto.record("yaml")
def test_cache_input_data(snapshot) -> None:
    data = snapshot(get_data(1))
    assert func(data) == 2


@pytest.fixture(scope="function")
def data(snapshot) -> int:
    return snapshot(get_data(1))


@ditto.record("yaml")
def test_use_cached_input_data_and_snapshot_result(snapshot, data) -> None:
    result = func(data)
    assert result == snapshot(result)