from ditto.marks import record


@record("yaml")
def test_asdf(snapshot):
    assert {"a": 1} == snapshot({"a": 1})
    assert {"x": 2} == snapshot({"x": 2}, suffix="x")


def test_what(snapshot):
    assert 2423 == snapshot(2423, suffix="zxcv sdf 23423")