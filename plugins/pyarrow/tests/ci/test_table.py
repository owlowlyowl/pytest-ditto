import pyarrow as pa

import ditto


def make_table() -> pa.Table:
    return pa.table(
        [
            [1, 2, 3],
            [4.5, 5.2, 6.8],
            [7, 8.5, None],
            [True, False, True],
            ["a", "b", "c"],
        ],
        names=[
            "ints",
            "floats",
            "floats_with_none",
            "bools",
            "strings",
        ],
    )


@ditto.pyarrow.parquet
def test_parquet_snapshot_matches_the_recorded_table(snapshot) -> None:
    """A table snapshotted as parquet equals the recorded snapshot."""
    table = make_table()

    actual = snapshot(table, "table")

    assert table.equals(actual)


@ditto.pyarrow.feather
def test_feather_snapshot_matches_the_recorded_table(snapshot) -> None:
    """A table snapshotted as feather equals the recorded snapshot."""
    table = make_table()

    actual = snapshot(table, "table")

    assert table.equals(actual)


@ditto.pyarrow.csv
def test_csv_snapshot_matches_the_recorded_table(snapshot) -> None:
    """A table snapshotted as CSV equals the recorded snapshot."""
    table = make_table()

    actual = snapshot(table, "table")

    assert table.equals(actual)
