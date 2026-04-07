from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from contextlib import AbstractContextManager


__all__ = ("PrefixedMapping",)


class PrefixedMapping(MutableMapping[str, bytes]):
    """Scopes all operations on a flat MutableMapping under a fixed key prefix.

    Use for flat key-value stores (Redis, DynamoDB, etc.) where namespace
    isolation must come from the key rather than a directory/root path.

    The prefix is prepended to keys on write and stripped on read. Keys
    exposed to callers are always prefix-free.

    __iter__ filters by prefix. For backends where full-keyspace iteration
    is expensive (large shared Redis DB), either:
      - Use a dedicated DB instance, OR
      - Configure the inner mapping to do prefix-scoped scanning natively, OR
      - Raise NotImplementedError on __iter__ to opt out of pruning.

    Context management is propagated to the inner store when it implements
    __enter__/__exit__. ditto enters the backend via the session ExitStack
    (in plugin.py) and closes it in pytest_unconfigure.
    """

    def __init__(self, store: MutableMapping[str, bytes], prefix: str) -> None:
        if not prefix:
            raise ValueError("prefix must be non-empty")
        self._store = store
        self._prefix = prefix

    def _full_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def __getitem__(self, key: str) -> bytes:
        return self._store[self._full_key(key)]

    def __setitem__(self, key: str, value: bytes) -> None:
        self._store[self._full_key(key)] = value

    def __delitem__(self, key: str) -> None:
        del self._store[self._full_key(key)]

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return self._full_key(key) in self._store

    def __iter__(self) -> Iterator[str]:
        n = len(self._prefix)
        for k in self._store:
            if k.startswith(self._prefix):
                yield k[n:]

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __enter__(self) -> "PrefixedMapping":
        if isinstance(self._store, AbstractContextManager):
            self._store.__enter__()
        return self

    def __exit__(self, *exc_info: object) -> None:
        if isinstance(self._store, AbstractContextManager):
            self._store.__exit__(*exc_info)
