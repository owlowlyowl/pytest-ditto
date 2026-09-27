# Custom Backends

Non-fsspec backends (Redis, PostgreSQL, DuckDB, etc.) are registered via the
`ditto_backends` entry-point group.

## Backend Factory

A backend factory receives the full URI string plus any matching kwargs from
`ditto_storage_options`, and returns a `MutableMapping[str, bytes]`:

```python
from collections.abc import MutableMapping


def create_my_backend(uri: str, **storage_options) -> MutableMapping[str, bytes]:
    """Create a backend mapping for the given URI.
    
    Parameters
    ----------
    uri : str
        The full target URI (e.g., "myscheme://host/path").
    **storage_options
        Kwargs from ditto_storage_options for this scheme.
    
    Returns
    -------
    MutableMapping[str, bytes]
        A mapping that stores snapshot data as bytes keyed by snapshot name.
    """
    ...
```

## Registration

Register the factory in `pyproject.toml`:

```toml
[project.entry-points.ditto_backends]
myscheme = "my_package:create_my_backend"
```

Once registered, `target="myscheme://..."` works in any mark:

```python
import ditto

@ditto.record("json", target="myscheme://my-host/snapshots")
def test_something(snapshot): ...
```

The entry-point name is the URI scheme: a lowercase letter followed by
lowercase letters, digits, `+`, `-` or `.`. `file` is handled by ditto itself,
so a `file` registration is never used.

### Loading and conflicts

ditto reads scheme names from package metadata and imports a backend's factory
only when a target first uses its scheme. An installed backend therefore costs
nothing in runs that don't use it, and a backend that fails to import only
affects the tests that target it: they fail with `DittoBackendLoadError`, which
names the scheme, the distribution and the original exception.

If two installed distributions register the same scheme, ditto doesn't pick
one: targets using that scheme fail with `DittoBackendConflictError`, naming
both distributions. A scheme that fails to load or conflicts never falls back
to an fsspec protocol of the same name.

`ditto doctor` imports every registered backend and reports load failures and
conflicts without running any tests.

### Registering in code

`ditto.backends.BACKEND_REGISTRY` is a mutable mapping. Setting a scheme, for
example from a `conftest.py`, overrides any installed factory for it and
resolves a conflict; deleting it restores the installed factory:

```python
import pytest
from ditto.backends import BACKEND_REGISTRY


@pytest.fixture(scope="session", autouse=True)
def my_backend():
    BACKEND_REGISTRY["myscheme"] = create_my_backend
    yield
    del BACKEND_REGISTRY["myscheme"]
```

## Context Manager Support

If your backend needs setup/teardown (connection pools, transactions), return
a context manager. pytest-ditto will enter it at session start and exit it at
session end:

```python
from contextlib import contextmanager
from collections.abc import MutableMapping


@contextmanager
def create_db_backend(uri: str, **opts) -> MutableMapping[str, bytes]:
    conn = connect(uri, **opts)
    try:
        yield DbMapping(conn)
    finally:
        conn.close()
```

## Example: Redis Backend

```python
import redis
from collections.abc import MutableMapping, Iterator


class RedisMapping(MutableMapping[str, bytes]):
    def __init__(self, client: redis.Redis, prefix: str):
        self._client = client
        self._prefix = prefix

    def _key(self, k: str) -> str:
        return f"{self._prefix}:{k}"

    def __getitem__(self, key: str) -> bytes:
        value = self._client.get(self._key(key))
        if value is None:
            raise KeyError(key)
        return value

    def __setitem__(self, key: str, value: bytes) -> None:
        self._client.set(self._key(key), value)

    def __delitem__(self, key: str) -> None:
        self._client.delete(self._key(key))

    def __iter__(self) -> Iterator[str]:
        prefix = self._prefix + ":"
        for key in self._client.scan_iter(f"{prefix}*"):
            yield key.decode().removeprefix(prefix)

    def __len__(self) -> int:
        return sum(1 for _ in self)


def create_redis_backend(uri: str, **storage_options) -> MutableMapping[str, bytes]:
    from urllib.parse import urlparse
    parsed = urlparse(uri)
    client = redis.Redis(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        db=int(parsed.path.lstrip("/") or "0"),
        **storage_options,
    )
    return RedisMapping(client, prefix="ditto")
```

Register it:

```toml
[project.entry-points.ditto_backends]
redis = "my_package.backends:create_redis_backend"
```

## Runnable Examples

See the [examples directory](https://github.com/owlowlyowl/pytest-ditto/tree/main/examples)
for self-contained PostgreSQL, Redis, and DuckDB examples.
