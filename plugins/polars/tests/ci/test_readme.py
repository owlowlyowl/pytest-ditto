import polars as pl
import polars.testing  # noqa: F401

import ditto


def awesome_fn_to_test(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(pl.col("a") * 2)


@ditto.polars.parquet
def test_fn_with_parquet_dataframe_snapshot(snapshot):
    """The README example: a transformed DataFrame matches its parquet snapshot."""
    input_data = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 9]})
    result = awesome_fn_to_test(input_data)
    pl.testing.assert_frame_equal(result, snapshot(result, key="ab_dataframe"))
