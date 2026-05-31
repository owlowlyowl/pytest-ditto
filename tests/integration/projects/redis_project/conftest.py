from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from contextlib import AbstractContextManager

import pytest
import redis

from ditto.backends import BACKEND_REGISTRY, PrefixedMapping


class RedisMapping(AbstractContextManager, MutableMapping[str, bytes]):
    def __init__(self, client: redis.Redis) -> None:
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

    def __iter__(self) -> Iterator[str]:
        return (item.decode() for item in self._client.scan_iter())

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return bool(self._client.exists(key))

    def __enter__(self) -> RedisMapping:
        return self

    def __exit__(self, *args: object) -> None:
        self._client.close()


@pytest.fixture(scope="session", autouse=True)
def _register_redis_backend() -> Iterator[None]:
    def create_redis_backend(
        uri: str,
        **storage_options: object,
    ) -> MutableMapping[str, bytes]:
        client = redis.Redis.from_url(uri, **storage_options)
        return PrefixedMapping(RedisMapping(client), prefix="ditto:")

    BACKEND_REGISTRY["redis"] = create_redis_backend
    yield
    BACKEND_REGISTRY.pop("redis", None)
