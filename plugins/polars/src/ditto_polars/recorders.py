import io

import polars as pl

from ditto.recorders import Recorder


__all__ = ("parquet", "ipc", "csv", "ndjson")


def _parquet_dumps(data: pl.DataFrame) -> bytes:
    buffer = io.BytesIO()
    data.write_parquet(buffer)
    return buffer.getvalue()


def _parquet_loads(raw: bytes) -> pl.DataFrame:
    return pl.read_parquet(raw)


parquet: Recorder[pl.DataFrame] = Recorder(dumps=_parquet_dumps, loads=_parquet_loads)


def _ipc_dumps(data: pl.DataFrame) -> bytes:
    buffer = io.BytesIO()
    data.write_ipc(buffer)
    return buffer.getvalue()


def _ipc_loads(raw: bytes) -> pl.DataFrame:
    return pl.read_ipc(raw)


ipc: Recorder[pl.DataFrame] = Recorder(dumps=_ipc_dumps, loads=_ipc_loads)


def _csv_dumps(data: pl.DataFrame) -> bytes:
    return data.write_csv().encode("utf-8")


def _csv_loads(raw: bytes) -> pl.DataFrame:
    return pl.read_csv(raw)


csv: Recorder[pl.DataFrame] = Recorder(dumps=_csv_dumps, loads=_csv_loads)


def _ndjson_dumps(data: pl.DataFrame) -> bytes:
    return data.write_ndjson().encode("utf-8")


def _ndjson_loads(raw: bytes) -> pl.DataFrame:
    return pl.read_ndjson(raw)


ndjson: Recorder[pl.DataFrame] = Recorder(dumps=_ndjson_dumps, loads=_ndjson_loads)
