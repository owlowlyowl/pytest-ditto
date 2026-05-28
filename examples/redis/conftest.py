from __future__ import annotations

import importlib
import importlib.util
import os
from collections.abc import Callable, Iterator, MutableMapping
from contextlib import AbstractContextManager
from typing import Protocol

import pytest

from ditto.backends import BACKEND_REGISTRY, PrefixedMapping


REDIS_TARGET = os.getenv("DITTO_REDIS_TARGET", "redis://localhost:6380/0")
BackendFactory = Callable[..., MutableMapping[str, bytes]]


def _load_redis() -> object:
    spec = importlib.util.find_spec("redis")
    if spec is None or (
        spec.origin is None and spec.submodule_search_locations is not None
    ):
        pytest.skip("redis example needs the redis package installed")
    return importlib.import_module("redis")


def _make_redis_backend(redis_module: object) -> BackendFactory:
    def create_redis_backend(
        uri: str, **storage_options: object
    ) -> MutableMapping[str, bytes]:
        client = redis_module.Redis.from_url(uri, **storage_options)
        return PrefixedMapping(RedisMapping(client), prefix="ditto:")

    return create_redis_backend


class RedisClient(Protocol):
    def get(self, key: str) -> bytes | None: ...

    def set(self, key: str, value: bytes) -> object: ...

    def delete(self, key: str) -> int: ...

    def exists(self, key: str) -> int: ...

    def scan_iter(self) -> Iterator[bytes]: ...

    def close(self) -> None: ...


class RedisMapping(AbstractContextManager, MutableMapping[str, bytes]):
    """Adapt a redis client to ditto's mutable-mapping backend protocol."""

    def __init__(self, client: RedisClient) -> None:
        self._client = client

    def __getitem__(self, key: str) -> bytes:
        value = self._client.get(key)
        if value is None:
            raise KeyError(key)
        return value

    def __setitem__(self, key: str, value: bytes) -> None:
        self._client.set(key, value)

    def __delitem__(self, key: str) -> None:
        if not self._client.delete(key):
            raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return bool(self._client.exists(key))

    def __iter__(self) -> Iterator[str]:
        return (item.decode() for item in self._client.scan_iter())

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __enter__(self) -> "RedisMapping":
        return self

    def __exit__(self, *args: object) -> None:
        self._client.close()


def _redis_connect_kwargs() -> dict[str, object]:
    kwargs: dict[str, object] = {}

    username = os.getenv("REDIS_USERNAME")
    if username:
        kwargs["username"] = username

    password = os.getenv("REDIS_PASSWORD")
    if password:
        kwargs["password"] = password

    return kwargs


@pytest.fixture(scope="session", autouse=True)
def _register_redis_backend() -> Iterator[None]:
    """Register the example redis:// backend and skip when Redis is unavailable."""
    redis_module = _load_redis()
    probe = redis_module.Redis.from_url(REDIS_TARGET, **_redis_connect_kwargs())

    try:
        probe.ping()
    except redis_module.exceptions.RedisError as exc:
        pytest.skip(
            "redis example needs the examples Docker container running at "
            f"{REDIS_TARGET!r}: {exc}"
        )
    finally:
        probe.close()

    BACKEND_REGISTRY["redis"] = _make_redis_backend(redis_module)
    yield
    BACKEND_REGISTRY.pop("redis", None)
