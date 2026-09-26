from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pa_csv
import pyarrow.feather as pa_feather
import pyarrow.parquet as pa_parquet

from ditto.recorders import Recorder


__all__ = ("parquet", "feather", "csv")


def _parquet_save(data: pa.Table, filepath: Path) -> None:
    pa_parquet.write_table(data, filepath)


def _parquet_load(filepath: Path) -> pa.Table:
    return pa_parquet.read_table(filepath)


parquet: Recorder[pa.Table] = Recorder(
    identifier="pyarrow.parquet", save=_parquet_save, load=_parquet_load
)


def _feather_save(data: pa.Table, filepath: Path) -> None:
    pa_feather.write_feather(data, filepath)


def _feather_load(filepath: Path) -> pa.Table:
    return pa_feather.read_table(filepath)


feather: Recorder[pa.Table] = Recorder(
    identifier="pyarrow.feather", save=_feather_save, load=_feather_load
)


def _csv_save(data: pa.Table, filepath: Path) -> None:
    pa_csv.write_csv(data, filepath)


def _csv_load(filepath: Path) -> pa.Table:
    return pa_csv.read_csv(filepath)


csv: Recorder[pa.Table] = Recorder(
    identifier="pyarrow.csv", save=_csv_save, load=_csv_load
)
