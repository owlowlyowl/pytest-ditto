from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from pyarrow import csv, feather

from ditto.recorders import Recorder


def _parquet_save(data: pa.Table, filepath: Path) -> None:
    pq.write_table(data, filepath)


def _parquet_load(filepath: Path) -> pa.Table:
    return pq.read_table(filepath)


pyarrow_parquet: Recorder[pa.Table] = Recorder(
    extension="pyarrow.parquet", save=_parquet_save, load=_parquet_load
)


def _feather_save(data: pa.Table, filepath: Path) -> None:
    feather.write_feather(data, filepath)


def _feather_load(filepath: Path) -> pa.Table:
    return feather.read_table(filepath)


pyarrow_feather: Recorder[pa.Table] = Recorder(
    extension="pyarrow.feather", save=_feather_save, load=_feather_load
)


def _csv_save(data: pa.Table, filepath: Path) -> None:
    csv.write_csv(data, filepath)


def _csv_load(filepath: Path) -> pa.Table:
    return csv.read_csv(filepath)


pyarrow_csv: Recorder[pa.Table] = Recorder(
    extension="pyarrow.csv", save=_csv_save, load=_csv_load
)
