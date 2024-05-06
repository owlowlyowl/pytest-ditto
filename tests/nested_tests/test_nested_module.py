import pytest

import ditto


def get_data(value: int) -> int:
    return value


def func(value: int) -> int:
    return value + 34


@ditto.record("yaml")
def test_cache_input_data(snapshot) -> None:
    x = 1
    data = snapshot(get_data(x), identifier="input_data")
    assert func(data) == func(x)


# TODO: A function scoped fixture that uses snapshot generates one shapshot file
#  per test and problematically, the name of the file is the same as the test name it is
#  called from. This means overwritten data.


# FIXME: handle use of snapshot from within fixtures.
@pytest.fixture(scope="function")
def data(snapshot) -> int:
    return snapshot(get_data(1), identifier="data")


@pytest.mark.xfail(
    reason="The `snapshot` fixture cannot be used from within other fixtures."
)
@ditto.record("yaml")
def test_input_data_is_a_fixture_that_uses_snapshot_to_cache_data(
    snapshot, data
) -> None:
    assert func(data) == snapshot(func(data))


@pytest.mark.xfail(
    reason="The `snapshot` fixture cannot be used from within other fixtures."
)
@ditto.record("yaml")
def test_use_cached_input_data_and_snapshot_result(snapshot, data) -> None:
    result = func(data)
    assert result == snapshot(result)


@pytest.mark.xfail(reason="Set to fail: 1 != 2")
def test_neq():
    assert 1 == 2
