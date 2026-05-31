import ditto


def fn(x: int) -> int:
    return x + 1  # original implementation
    # return x + 2  # new implementation


def test_fn(snapshot) -> None:
    x = 1
    result = fn(x)
    assert result == snapshot(result, key="fn")


@ditto.record("json", target="file://.tmp")
def test_fn_backend(snapshot) -> None:
    x = 1
    result = fn(x)
    assert result == snapshot(result, key="fn")
