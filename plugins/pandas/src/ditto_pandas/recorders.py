from pathlib import Path

import pandas as pd

from ditto.recorders._protocol import Recorder


def _parquet_save(data: pd.DataFrame, filepath: Path) -> None:
    data.to_parquet(filepath)


def _parquet_load(filepath: Path) -> pd.DataFrame:
    return pd.read_parquet(filepath)


pandas_parquet: Recorder[pd.DataFrame] = Recorder(
    extension="pandas.parquet", save=_parquet_save, load=_parquet_load
)


def _json_save(data: pd.DataFrame, filepath: Path) -> None:
    data.to_json(filepath, orient="table")


def _json_load(filepath: Path) -> pd.DataFrame:
    return pd.read_json(filepath, orient="table")


pandas_json: Recorder[pd.DataFrame] = Recorder(
    extension="pandas.json", save=_json_save, load=_json_load
)


def _csv_save(data: pd.DataFrame, filepath: Path) -> None:
    data.to_csv(filepath)


def _csv_load(filepath: Path) -> pd.DataFrame:
    return pd.read_csv(filepath, index_col=0)


pandas_csv: Recorder[pd.DataFrame] = Recorder(
    extension="pandas.csv", save=_csv_save, load=_csv_load
)
