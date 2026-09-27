from pathlib import Path

import pandas as pd

from ditto.recorders import Recorder


__all__ = ("parquet", "json", "csv")


def _parquet_save(data: pd.DataFrame, filepath: Path) -> None:
    data.to_parquet(filepath)


def _parquet_load(filepath: Path) -> pd.DataFrame:
    return pd.read_parquet(filepath)


parquet: Recorder[pd.DataFrame] = Recorder(save=_parquet_save, load=_parquet_load)


def _json_save(data: pd.DataFrame, filepath: Path) -> None:
    data.to_json(filepath, orient="table")


def _json_load(filepath: Path) -> pd.DataFrame:
    return pd.read_json(filepath, orient="table")


json: Recorder[pd.DataFrame] = Recorder(save=_json_save, load=_json_load)


def _csv_save(data: pd.DataFrame, filepath: Path) -> None:
    data.to_csv(filepath)


def _csv_load(filepath: Path) -> pd.DataFrame:
    # to_csv writes the index as the first column; read it back as the index,
    # not as an "Unnamed: 0" data column (#40).
    return pd.read_csv(filepath, index_col=0)


csv: Recorder[pd.DataFrame] = Recorder(save=_csv_save, load=_csv_load)
