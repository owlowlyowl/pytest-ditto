from ditto.io.protocol import SnapshotIO
from ditto.io._yaml import YamlIO
from ditto.io._json import JsonIO
from ditto.io._pickle import PickleIO
from ditto.io._pandas_parquet import PandasParquetIO


__all__ = ["SnapshotIO", "YamlIO", "JsonIO", "PickleIO", "PandasParquetIO"]


IO_MAP: dict[str, type[SnapshotIO]] = {
    "pkl": PickleIO,
    "json": JsonIO,
    "yaml": YamlIO,
    "pandas_parquet": PandasParquetIO,
}


def register_io(name: str, io: type[SnapshotIO]) -> None:
    IO_MAP[name] = io


def io_default() -> type[SnapshotIO]:
    return PickleIO
