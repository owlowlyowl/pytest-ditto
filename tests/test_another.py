import ditto


@ditto.record("yaml", name="custom-name-xyz")
def test_asdf(snapshot):
    assert {"a": 1} == snapshot({"a": 1})
    assert {"x": 2} == snapshot({"x": 2}, identifier="x")


def test_what(snapshot):
    assert 2423 == snapshot(2423, identifier="zxcv sdf 23423")