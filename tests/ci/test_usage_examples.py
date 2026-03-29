import pytest

import ditto


@ditto.yaml
def test_roundtrips_dict_through_yaml_format(snapshot) -> None:
    """snapshot round-trips dict values produced by a pure function."""
    def fn(x: dict[str, int]) -> dict[str, int]:
        return {k: v + 1 for k, v in x.items()}

    result_a = fn({"a": 1})
    result_x = fn({"x": 2})

    actual_a = snapshot(result_a, key="a")
    actual_x = snapshot(result_x, key="x")

    assert actual_a == result_a
    assert actual_x == result_x


@ditto.pickle
@pytest.mark.parametrize(
    ("a", "b"),
    [
        pytest.param(1, 2, id="First"),
        pytest.param(3, 4, id="Second"),
    ],
)
def test_roundtrips_parametrised_ints_through_pickle(snapshot, a, b) -> None:
    """Each parametrised set stores and retrieves values independently."""
    actual_a = snapshot(a, key="a")
    actual_b = snapshot(b, key="b")

    assert actual_a == a
    assert actual_b == b


@ditto.json
def test_roundtrips_string_through_json_format(snapshot) -> None:
    """snapshot round-trips a transformed string through JSON format."""
    input_str = "abc"

    def fn(x: str) -> str:
        return f"{x}def"

    result = fn(input_str)
    actual = snapshot(result, key="abc")

    assert actual == result
