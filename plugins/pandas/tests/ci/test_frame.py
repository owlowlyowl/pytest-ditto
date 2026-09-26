import pandas as pd

import ditto


def make_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "ints": [1, 2, 3],
        "floats": [4.5, 5.2, 6.8],
        "strings": ["a", "b", "c"],
    })


@ditto.pandas.parquet
def test_parquet_snapshot_matches_the_recorded_frame(snapshot) -> None:
    """A DataFrame snapshotted as parquet equals the recorded snapshot."""
    df = make_frame()

    actual = snapshot(df, "frame")

    pd.testing.assert_frame_equal(actual, df)


@ditto.pandas.json
def test_json_snapshot_matches_the_recorded_frame(snapshot) -> None:
    """A DataFrame snapshotted as JSON equals the recorded snapshot."""
    df = make_frame()

    actual = snapshot(df, "frame")

    pd.testing.assert_frame_equal(actual, df)


@ditto.pandas.csv
def test_csv_snapshot_matches_the_recorded_frame(snapshot) -> None:
    """A DataFrame snapshotted as CSV equals the recorded snapshot.

    check_index_type=False: CSV does not preserve index type — see README.
    """
    df = make_frame()

    actual = snapshot(df, "frame")

    pd.testing.assert_frame_equal(actual, df, check_index_type=False)
