# Importing from `ditto.io._plugins` runs the `_load_plugins` function which will
# discover and register any internal and externally registered IO class plugins.
# Plugins are imported first so no internal IO plugins are overwritten. If necessary,
# internal plugins can be overwitten using the `register` function.
from ditto.io._plugins import IO_REGISTRY
from ditto.io._protocol import Base
from ditto.io._pickle import Pickle


__all__ = [
    "Base",
    "register",
    "get",
    "default",
]


def register(name: str, io: type[Base]) -> None:
    IO_REGISTRY[name] = io


def get(name: str, default: type[Base] = Pickle) -> type[Base]:
    return IO_REGISTRY.get(name, default)


def default() -> type[Base]:
    return Pickle
