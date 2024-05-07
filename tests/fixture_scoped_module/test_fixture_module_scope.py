import pytest

import ditto


def get_data(value: int) -> int:
    return value


def func(value: int) -> int:
    return value + 34


@pytest.fixture(scope="module")
def data_fixture_with_id(snapshot) -> int:
    return snapshot(get_data(1), key="data")


@pytest.fixture(scope="module")
def data_fixture_no_id(snapshot) -> int:
    return snapshot(get_data(1))


@pytest.mark.xfail(
    reason="The `snapshot` fixture cannot be used from within other fixtures."
)
@ditto.record("yaml")
def test_calling_test_with_id(snapshot, data_fixture_with_id) -> None:
    assert func(data_fixture_with_id) == snapshot(func(data_fixture_with_id))


@pytest.mark.xfail(
    reason="The `snapshot` fixture cannot be used from within other fixtures."
)
@ditto.record("yaml")
def test_calling_test_no_id(snapshot, data_fixture_no_id) -> None:
    assert func(data_fixture_no_id) == snapshot(func(data_fixture_no_id))
