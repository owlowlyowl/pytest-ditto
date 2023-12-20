import pytest

import ditto


def get_data(value):
    return value


def func(value):
    return value + 2


@ditto.record("yaml")
def test_xcv(snapshot):
    data = snapshot(get_data(1))
    assert func(data) == 2


@pytest.fixture(scope="function")
def data(snapshot):
    return snapshot(get_data(1))


@ditto.record("yaml")
def test_qqq(snapshot, data):
    f = func(data)
    assert f == snapshot(f)