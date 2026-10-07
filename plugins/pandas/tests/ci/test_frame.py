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


def make_series() -> pd.Series:
    return pd.Series(
        [1.0, 2.0, 3.0],
        name="x",
        index=pd.Index(["a", "b", "c"], name="k"),
    )


@ditto.pandas.parquet
def test_parquet_snapshot_matches_the_recorded_series(snapshot) -> None:
    """A Series snapshotted as parquet equals the recorded snapshot."""
    series = make_series()

    actual = snapshot(series, "series")

    pd.testing.assert_series_equal(actual, series)


@ditto.pandas.json
def test_json_snapshot_matches_the_recorded_series(snapshot) -> None:
    """A Series snapshotted as JSON equals the recorded snapshot."""
    series = make_series()

    actual = snapshot(series, "series")

    pd.testing.assert_series_equal(actual, series)


@ditto.pandas.csv
def test_csv_snapshot_matches_the_recorded_series(snapshot) -> None:
    """A Series snapshotted as CSV equals the recorded snapshot.

    check_index_type=False: CSV does not preserve index type — see README.
    """
    series = make_series()

    actual = snapshot(series, "series")

    pd.testing.assert_series_equal(actual, series, check_index_type=False)


@ditto.pandas.parquet
def test_parquet_snapshot_keeps_the_index_freq(snapshot) -> None:
    """A time-series frame matches its snapshot with the default check_freq (#178)."""
    # unit="us": pandas 2 defaults to "ns" and pandas 3 to "us", and the
    # snapshot has to match on both.
    index = pd.date_range("2020-01-01", periods=3, unit="us")
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0]}, index=index)

    actual = snapshot(df, "frame")

    pd.testing.assert_frame_equal(actual, df)
