import pandas as pd

import ditto


@ditto.pandas.parquet
def test_parquet_mark_records_snapshot_as_parquet_file(snapshot) -> None:
    """@ditto.pandas.parquet records a DataFrame snapshot as a parquet file."""
    df = pd.DataFrame({"a": [44, 77], "qwer": [3, 4]})

    recorded = snapshot(df, key="snapshot")

    pd.testing.assert_frame_equal(recorded, df)
    assert snapshot.filepath("snapshot").suffix == ".parquet"


@ditto.pandas.json
def test_json_mark_records_snapshot_as_json_file(snapshot) -> None:
    """@ditto.pandas.json records a DataFrame snapshot as a json file."""
    df = pd.DataFrame({"a": [44, 77], "qwer": [3, 4]})

    recorded = snapshot(df, key="snapshot")

    pd.testing.assert_frame_equal(recorded, df)
    assert snapshot.filepath("snapshot").suffix == ".json"


@ditto.pandas.csv
def test_csv_mark_records_snapshot_as_csv_file(snapshot) -> None:
    """@ditto.pandas.csv records a DataFrame snapshot as a csv file.

    check_index_type=False: CSV does not preserve index type — see README.
    """
    df = pd.DataFrame({"a": [44, 77], "qwer": [3, 4]})

    recorded = snapshot(df, key="snapshot")

    pd.testing.assert_frame_equal(recorded, df, check_index_type=False)
    assert snapshot.filepath("snapshot").suffix == ".csv"
