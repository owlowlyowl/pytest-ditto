import pytest

import ditto


@ditto.record("yaml")
def test_asdf(snapshot):
    assert {"a": 1} == snapshot({"a": 1})
    assert {"x": 2} == snapshot({"x": 2}, suffix="x")


@ditto.record("pkl", zxcv=1)
@pytest.mark.parametrize(
    "a,b",
    [
        pytest.param(1, 2, id="HERE IS THE ID"),
        # (3, 4),
        (1, 2),
    ],
)
def test_qwe(snapshot, a, b):
    assert a == snapshot(1, suffix="a")
    assert b == snapshot(2)


@ditto.record("json")
def test_cvn(snapshot):
    assert "this string" == snapshot("this string")