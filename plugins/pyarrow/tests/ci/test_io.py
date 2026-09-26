import pyarrow as pa

import ditto


def make_table() -> pa.Table:
    return pa.table(
        [
            [1, 2, 3],
            [4.0, 5.0, 6.0],
            [7, 8.0, None],
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
def test_parquet(snapshot) -> None:
    key = "ijk"
    snapshot(make_table(), key=key)
    assert snapshot.filepath(key).exists()
    assert snapshot.filepath(key).suffix == ".parquet"


@ditto.pyarrow.feather
def test_feather(snapshot) -> None:
    key = "marks"
    snapshot(make_table(), key=key)
    assert snapshot.filepath(key).exists()
    assert snapshot.filepath(key).suffix == ".feather"


# @ditto.pyarrow.orc
# def test_orc(snapshot) -> None:
#     key = "marks"
#     snapshot(make_table(), key=key)
#     assert snapshot.filepath(key).exists()
#     assert snapshot.filepath(key).suffix == ".orc"
#


@ditto.pyarrow.csv
def test_csv(snapshot) -> None:
    key = "marks"
    snapshot(make_table(), key=key)
    assert snapshot.filepath(key).exists()
    assert snapshot.filepath(key).suffix == ".csv"
