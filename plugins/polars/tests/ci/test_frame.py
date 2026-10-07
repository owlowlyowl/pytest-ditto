import polars as pl
import polars.testing  # noqa: F401

import ditto


def make_frame() -> pl.DataFrame:
    return pl.DataFrame({
        "ints": [1, 2, 3],
        "floats": [4.5, 5.2, 6.8],
        "strings": ["a", "b", "c"],
    })


@ditto.polars.parquet
def test_parquet_snapshot_matches_the_recorded_frame(snapshot) -> None:
    """A DataFrame snapshotted as parquet equals the recorded snapshot."""
    df = make_frame()

    actual = snapshot(df, "frame")

    pl.testing.assert_frame_equal(actual, df)


@ditto.polars.ipc
def test_ipc_snapshot_matches_the_recorded_frame(snapshot) -> None:
    """A DataFrame snapshotted as IPC equals the recorded snapshot."""
    df = make_frame()

    actual = snapshot(df, "frame")

    pl.testing.assert_frame_equal(actual, df)


@ditto.polars.csv
def test_csv_snapshot_matches_the_recorded_frame(snapshot) -> None:
    """A DataFrame snapshotted as CSV equals the recorded snapshot."""
    df = make_frame()

    actual = snapshot(df, "frame")

    pl.testing.assert_frame_equal(actual, df)


@ditto.polars.ndjson
def test_ndjson_snapshot_matches_the_recorded_frame(snapshot) -> None:
    """A DataFrame snapshotted as NDJSON equals the recorded snapshot."""
    df = make_frame()

    actual = snapshot(df, "frame")

    pl.testing.assert_frame_equal(actual, df)
