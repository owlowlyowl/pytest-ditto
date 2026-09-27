from pathlib import Path

import polars as pl

from ditto.recorders import Recorder


__all__ = ("parquet", "ipc", "csv", "ndjson")


def _parquet_save(data: pl.DataFrame, filepath: Path) -> None:
    data.write_parquet(filepath)


def _parquet_load(filepath: Path) -> pl.DataFrame:
    return pl.read_parquet(filepath)


parquet: Recorder[pl.DataFrame] = Recorder(save=_parquet_save, load=_parquet_load)


def _ipc_save(data: pl.DataFrame, filepath: Path) -> None:
    data.write_ipc(filepath)


def _ipc_load(filepath: Path) -> pl.DataFrame:
    return pl.read_ipc(filepath)


ipc: Recorder[pl.DataFrame] = Recorder(save=_ipc_save, load=_ipc_load)


def _csv_save(data: pl.DataFrame, filepath: Path) -> None:
    data.write_csv(filepath)


def _csv_load(filepath: Path) -> pl.DataFrame:
    return pl.read_csv(filepath)


csv: Recorder[pl.DataFrame] = Recorder(save=_csv_save, load=_csv_load)


def _ndjson_save(data: pl.DataFrame, filepath: Path) -> None:
    data.write_ndjson(filepath)


def _ndjson_load(filepath: Path) -> pl.DataFrame:
    return pl.read_ndjson(filepath)


ndjson: Recorder[pl.DataFrame] = Recorder(save=_ndjson_save, load=_ndjson_load)
