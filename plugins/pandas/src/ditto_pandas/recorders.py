import io

import pandas as pd

from ditto.recorders import Recorder


__all__ = ("parquet", "json", "csv")


def _parquet_dumps(data: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    data.to_parquet(buffer)
    return buffer.getvalue()


def _parquet_loads(raw: bytes) -> pd.DataFrame:
    return pd.read_parquet(io.BytesIO(raw))


parquet: Recorder[pd.DataFrame] = Recorder(dumps=_parquet_dumps, loads=_parquet_loads)


def _json_dumps(data: pd.DataFrame) -> bytes:
    buffer = io.StringIO()
    data.to_json(buffer, orient="table")
    return buffer.getvalue().encode("utf-8")


def _json_loads(raw: bytes) -> pd.DataFrame:
    return pd.read_json(io.StringIO(raw.decode("utf-8")), orient="table")


json: Recorder[pd.DataFrame] = Recorder(dumps=_json_dumps, loads=_json_loads)


def _csv_dumps(data: pd.DataFrame) -> bytes:
    # "\n" rather than the platform's line separator, so the bytes are the same
    # on every platform.
    return data.to_csv(lineterminator="\n").encode("utf-8")


def _csv_loads(raw: bytes) -> pd.DataFrame:
    # to_csv writes the index as the first column; read it back as the index,
    # not as an "Unnamed: 0" data column (#40).
    return pd.read_csv(io.BytesIO(raw), index_col=0)


csv: Recorder[pd.DataFrame] = Recorder(dumps=_csv_dumps, loads=_csv_loads)
