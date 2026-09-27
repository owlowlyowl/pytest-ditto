import pyarrow as pa
import pyarrow.csv as pa_csv
import pyarrow.feather as pa_feather
import pyarrow.parquet as pa_parquet

from ditto.recorders import Recorder


__all__ = ("parquet", "feather", "csv")


def _parquet_dumps(data: pa.Table) -> bytes:
    sink = pa.BufferOutputStream()
    pa_parquet.write_table(data, sink)
    return sink.getvalue().to_pybytes()


def _parquet_loads(raw: bytes) -> pa.Table:
    return pa_parquet.read_table(pa.BufferReader(raw))


parquet: Recorder[pa.Table] = Recorder(dumps=_parquet_dumps, loads=_parquet_loads)


def _feather_dumps(data: pa.Table) -> bytes:
    sink = pa.BufferOutputStream()
    pa_feather.write_feather(data, sink)
    return sink.getvalue().to_pybytes()


def _feather_loads(raw: bytes) -> pa.Table:
    return pa_feather.read_table(pa.BufferReader(raw))


feather: Recorder[pa.Table] = Recorder(dumps=_feather_dumps, loads=_feather_loads)


def _csv_dumps(data: pa.Table) -> bytes:
    sink = pa.BufferOutputStream()
    pa_csv.write_csv(data, sink)
    return sink.getvalue().to_pybytes()


def _csv_loads(raw: bytes) -> pa.Table:
    return pa_csv.read_csv(pa.BufferReader(raw))


csv: Recorder[pa.Table] = Recorder(dumps=_csv_dumps, loads=_csv_loads)
