import pytest

import ditto


@ditto.yaml
def test_yaml_dict_snapshot(snapshot):
    def fn(x: dict[str, int]) -> dict[str, int]:
        return {k: v + 1 for k, v in x.items()}

    assert fn({"a": 1}) == snapshot(fn({"a": 1}), key="a")
    assert fn({"x": 2}) == snapshot(fn({"x": 2}), key="x")


@ditto.pickle
@pytest.mark.parametrize(
    ("a", "b"),
    [
        pytest.param(1, 2, id="First"),
        pytest.param(3, 4, id="Second"),
    ],
)
def test_pickle_int_snapshot_with_parametrize(snapshot, a, b):
    """
    Each param set should be saved with filenames as per below:
    - test_pickle_int_snapshot_with_parametrize[First]@a.pkl
    - test_pickle_int_snapshot_with_parametrize[First]@b.pkl
    - test_pickle_int_snapshot_with_parametrize[Second]@a.pkl
    - test_pickle_int_snapshot_with_parametrize[Second]@b.pkl
    """

    def fn(x: int) -> int:
        return x

    assert fn(a) == snapshot(fn(a), key="a")
    assert fn(b) == snapshot(fn(b), key="b")


@ditto.json
def test_json_single_string_snapshot(snapshot):

    input_str = "abc"

    def fn(x: str) -> str:
        return f"{x}def"

    assert fn(input_str) == snapshot(fn(input_str), key="abc")
