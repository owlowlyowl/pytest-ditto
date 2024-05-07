import pytest
import pandas as pd

import ditto


@ditto.record("yaml")
def test_yaml_dict_snapshot(snapshot):
    def fn(x: dict[str, int]) -> dict[str, int]:
        return {k: v + 1 for k, v in x.items()}

    assert fn({"a": 1}) == snapshot(fn({"a": 1}), key="a")
    assert fn({"x": 2}) == snapshot(fn({"x": 2}), key="x")


@ditto.record("pkl", key="custom-test-id-xyz")
@pytest.mark.parametrize(
    "a,b",
    [
        pytest.param(1, 2, id="First"),
        pytest.param(
            3,
            4,
            id="Second",
            marks=pytest.mark.xfail(
                reason="Expecting to fail as this is run second with different",
                raises=AssertionError,
            ),
        ),
    ],
)
def test_pickle_int_snapshot_when_changing_params(snapshot, a, b):

    def fn(x: int) -> int:
        return x

    assert fn(a) == snapshot(fn(a), key="custom-data-id-abc")
    assert fn(b) == snapshot(fn(b), key="b")


@ditto.record("json")
def test_json_single_string_snapshot(snapshot):

    input_str = "abc"

    def fn(x: str) -> str:
        return f"{x}def"

    assert fn(input_str) == snapshot(fn(input_str), key="abc")


@ditto.record("pandas_parquet")
def test_save_pandas_dataframe(snapshot):

    input_data = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 9]})

    def fn(df: pd.DataFrame):
        df["a"] *= 2
        return df

    result = fn(input_data)

    pd.testing.assert_frame_equal(result, snapshot(result, key="zzz"))
