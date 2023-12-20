from __future__ import annotations

from ditto.io._pickle import PickleIO
from ditto.io._json import JsonIO
from ditto.io._yaml import YamlIO
from ditto.io.protocol import SnapshotIO


IO_MAP: dict[str, SnapshotIO] = {
    "pkl": PickleIO(),
    "json": JsonIO(),
    "yaml": YamlIO(),
}


def register_io(name: str, io: SnapshotIO) -> None:
    IO_MAP[name] = io


def io_default() -> SnapshotIO:
    return PickleIO()
