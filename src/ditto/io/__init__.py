from ditto.io._plugins import IO_REGISTRY
from ditto.io._protocol import Base
from ditto.io._pickle import Pickle


__all__ = [
    "Base",
    "register",
    "get",
    "default",
]


def register(name: str, io: type[Base], registry: dict = IO_REGISTRY) -> None:
    # registry defaults to the module-level IO_REGISTRY but can be overridden
    # in tests to avoid mutating shared state.
    registry[name] = io


def get(
    name: str,
    registry: dict = IO_REGISTRY,
    default: type[Base] = Pickle,
) -> type[Base]:
    # registry defaults to the module-level IO_REGISTRY but can be overridden
    # in tests to pass a known, isolated set of handlers.
    return registry.get(name, default)


def default() -> type[Base]:
    return Pickle
