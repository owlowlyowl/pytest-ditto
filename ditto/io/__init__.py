from enum import Enum

from ditto.io._protocol import Base
from ditto.io._yaml import Yaml
from ditto.io._json import Json
from ditto.io._pickle import Pickle
from ditto.io._pandas_parquet import PandasParquet


__all__ = [
    "Base",
    "Yaml",
    "Json",
    "Pickle",
    "PandasParquet",
    "register",
    "get",
    "default",
]


class IO(str, Enum):
    PICKLE = "pickle"
    JSON = "json"
    YAML = "yaml"
    PANDAS_PARQUET = "pandas_parquet"


_NAME_IO_MAP: dict[str, type[Base]] = {
    IO.PICKLE: Pickle,
    IO.JSON: Json,
    IO.YAML: Yaml,
    IO.PANDAS_PARQUET: PandasParquet,
}


def register(name: str, io: type[Base]) -> None:
    _NAME_IO_MAP[name] = io


def get(name: str, default: type[Base] = Pickle) -> type[Base]:
    return _NAME_IO_MAP.get(name, default)


def default() -> type[Base]:
    return Pickle
