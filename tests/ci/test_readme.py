# import pandas as pd

# import ditto


# def fn(x: int) -> int:
#     return x + 1  # original implementation
#     # return x + 2  # new implementation


# def test_fn(snapshot) -> None:
#     x = 1
#     result = fn(x)
#     assert result == snapshot(result, key="fn")


# def awesome_fn_to_test(df: pd.DataFrame):
#     df.loc[:, "a"] *= 2
#     return df


# @ditto.pandas.parquet
# def test_fn_with_parquet_dataframe_snapshot(snapshot):
#     input_data = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 9]})
#     result = awesome_fn_to_test(input_data)
#     pd.testing.assert_frame_equal(result, snapshot(result, key="ab_dataframe"))


# @ditto.pandas.json
# def test_fn_with_json_dataframe_snapshot(snapshot):
#     input_data = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 9]})
#     result = awesome_fn_to_test(input_data)
#     pd.testing.assert_frame_equal(result, snapshot(result, key="ab_dataframe"))