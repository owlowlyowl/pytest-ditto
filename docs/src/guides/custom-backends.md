# Custom Backends

A backend is where ditto keeps snapshot data. Out of the box, ditto can store
snapshots on the local filesystem and anywhere [fsspec](https://filesystem-spec.readthedocs.io/)
can reach: S3, Google Cloud Storage, Azure, an in-memory filesystem and more
(see [Storage Backends](backends.md)). You only need a custom backend to store
snapshots somewhere fsspec doesn't cover, such as Redis, PostgreSQL or DuckDB.

A custom backend has two parts:

1. A **factory**: a function that takes a target URI and returns a mapping
   object that ditto reads and writes snapshots through.
2. A **scheme**: the name at the start of a target URI, such as the `redis` in
   `redis://localhost:6379/0`, which tells ditto to call your factory.

## Schemes and target URIs

Every snapshot target is a URI. ditto uses the URI's scheme, the part before
the first `:`, to decide which backend stores the snapshots:

```
redis://localhost:6379/0
└─┬─┘   └──────┬───────┘
scheme    the rest: its meaning is up to the backend
```

Everything after the scheme belongs to the backend. ditto passes the whole URI
to your factory unchanged (only `file://` URIs are rewritten, to make relative
paths absolute), so your factory decides what the host, path and query mean.
The URI is the same string users write in `target=`, `ditto_target` or a
target profile:

```python
import ditto


@ditto.record("json", target="redis://localhost:6379/0")
def test_user(snapshot): ...
```

### How ditto chooses a backend

For each target, ditto checks, in order:

| Order | Scheme | Stored by |
| --- | --- | --- |
| 1 | `file` | ditto itself, on the local filesystem |
| 2 | a scheme with a registered backend | that backend's factory |
| 3 | an fsspec protocol, such as `s3` or `memory` | fsspec |
| 4 | anything else | nothing: the test fails with `ValueError: Unknown backend scheme` |

Because registered backends come before fsspec, registering a scheme that
fsspec also knows, such as `s3`, replaces fsspec for those targets. `file`
can't be replaced.

### Choosing a scheme

A scheme is a lowercase letter followed by any mix of lowercase letters,
digits, `+`, `-` and `.`. This is the rule URIs themselves follow
([RFC 3986](https://www.rfc-editor.org/rfc/rfc3986#section-3.1)), restricted to
lowercase:

| Scheme | Valid | Why |
| --- | --- | --- |
| `redis` | yes | |
| `postgresql+psycopg` | yes | `+` often names a driver or transport |
| `my-store`, `acme.kv`, `kv2` | yes | `-`, `.` and digits are allowed after the first letter |
| `Redis` | no | must be lowercase |
| `2fa` | no | must start with a letter |
| `my_store` | no | `_` is not allowed |
| `file` | no | ditto stores `file://` targets itself |

Targets are matched case-insensitively, so `REDIS://localhost` also reaches the
`redis` backend.

All installed packages share one set of scheme names, and two packages that
register the same scheme [conflict](#when-a-backend-cant-be-used). Before
using a generic name such as `redis` in a package you publish, consider a more
specific one, such as `acme-redis`.

## Writing a factory

A factory has this signature:

```python
from collections.abc import MutableMapping


def create_backend(uri: str, **storage_options) -> MutableMapping[str, bytes]: ...
```

- `uri` is the target URI, exactly as the user wrote it.
- `storage_options` are keyword arguments for this target, usually
  credentials or connection settings. For a URI given with `target=` or
  `ditto_target`, they are the entry for your scheme in the
  [`ditto_storage_options`](backends.md#credentials-and-connection-settings-ditto_storage_options)
  fixture. For a [target profile](backends.md#named-profiles),
  they are the profile's own `storage_options`. Without either, there are none.
- The return value is the mapping that ditto stores snapshots in, described in
  the next section.

ditto calls a factory once per session for each distinct URI and set of
storage options, and reuses the mapping it returns for every test with the same
target. The same URI with two different sets of storage options gets two
separate mappings.

### The mapping

The factory returns a `collections.abc.MutableMapping[str, bytes]`: an object
with the same interface as a `dict` of strings to bytes. Subclass
`MutableMapping` and implement its five abstract methods; it provides `in`,
`get` and the other `dict` methods on top of them. ditto uses them as follows:

| Method | ditto uses it to |
| --- | --- |
| `__getitem__` | read a snapshot. Raise `KeyError` for a missing key: `in` relies on it to tell ditto a snapshot doesn't exist yet. |
| `__setitem__` | write a snapshot |
| `__delitem__` | remove a snapshot, in `ditto prune` |
| `__iter__` | list the stored keys, in `ditto verify`, `ditto prune` and the `--live` mode of `ditto list`, `status`, `stats` and `lint` |
| `__len__` | nothing directly, but `MutableMapping` requires it; `sum(1 for _ in self)` is enough |

Each key names one snapshot by its test module, test, snapshot key and a short
hash of them, and ends with the name of the recorder that wrote it:

```
tests/api/test_users/test_create@response~90e755f5c20755bd.json
└────────┬─────────┘ └────┬────┘ └──┬───┘ └──────┬───────┘ └┬─┘
    test module         test       key         hash     recorder
```

Keys are ASCII apart from the test module, which is the test file's path. They
contain `/`, `@`, `~` and `.`, so store them verbatim or encode them in a way
you can reverse. Values are the bytes the recorder produced; store and return
them unchanged.

`ditto verify` and `ditto prune` compare the keys that `__iter__` lists with
`ditto.lock`. A listed key under one of the project's test modules that the
lock doesn't record is reported by `verify` and deleted by `prune`; keys
outside those modules are left alone. If several projects share one store,
their test modules can have the same paths, so keep their keys apart with
`ditto.backends.PrefixedMapping`. It adds a prefix to every key on the way in,
strips it on the way out, and lists only keys that carry the prefix:

```python
from ditto.backends import PrefixedMapping

return PrefixedMapping(RedisMapping(client), prefix="my-project:")
```

### Opening and closing connections

If the mapping holds a connection, make it a context manager by giving it
`__enter__` and `__exit__` methods. ditto enters it the first time a test uses
its target, and exits it when the test session ends:

```python
from collections.abc import MutableMapping


class DbMapping(MutableMapping[str, bytes]):
    def __init__(self, uri: str, **options) -> None:
        self._conn = connect(uri, **options)

    def __enter__(self) -> "DbMapping":
        return self

    def __exit__(self, *exc_info) -> None:
        self._conn.close()

    ...  # the five mapping methods


def create_db_backend(uri: str, **storage_options) -> MutableMapping[str, bytes]:
    return DbMapping(uri, **storage_options)
```

ditto uses whatever `__enter__` returns as the mapping, so `__enter__`
normally returns `self`. `PrefixedMapping` passes `__enter__` and `__exit__`
through to the mapping it wraps.

## Registering the backend

There are two ways to connect a scheme to a factory:

- **In a package's metadata**, for a backend you install or publish. This is
  the usual way.
- **In code**, usually in a `conftest.py`, for a backend that lives with one
  project's tests, or to override an installed one.

### From a package

Add an entry point in the `ditto_backends` group to the package's
`pyproject.toml`. The entry-point name is the scheme, and the value is the
factory, written as `module:function`:

```toml
[project.entry-points.ditto_backends]
redis = "my_package.backends:create_redis_backend"
```

Entry points are read from the metadata of installed packages, so the package
must be installed, and reinstalled whenever this table changes. An editable
install (`pip install -e .`) counts. Once it is installed, any test in the
environment can use `target="redis://..."`.

ditto reads scheme names without importing anything, and imports the factory
only when a target first uses its scheme. An installed backend therefore adds
nothing to test runs that don't use it.

### From code

`ditto.backends.BACKEND_REGISTRY` maps every scheme ditto knows to its
factory. It is read-only. To register a factory in code, set it on
`BACKEND_REGISTRY.overrides`, which behaves like a `dict`:

```python
# conftest.py
import pytest
from ditto.backends import BACKEND_REGISTRY

from my_package.backends import create_redis_backend


@pytest.fixture(scope="session", autouse=True)
def redis_backend():
    BACKEND_REGISTRY.overrides["redis"] = create_redis_backend
    yield
    del BACKEND_REGISTRY.overrides["redis"]
```

Setting an override checks that the factory is callable and that the scheme
is valid. An override takes precedence over any installed backend for the same
scheme, including one that fails to import or conflicts with another package.
Deleting the override makes the installed backend available again.

Set overrides before any test uses the scheme, as the session fixture above
does. For the whole session, ditto builds every backend for a target URI with
the same factory. `ditto.lock`, `ditto verify` and `ditto prune` treat a URI as
one store, so every backend for it, including ones with different storage
options, must reach the same data. Once a test has used a target, a different
factory for its scheme fails the next test that uses it with
`DittoBackendChangedError`, rather than being silently ignored or splitting the
target's snapshots across two stores.

To give one test a throwaway store, give it a target of its own instead of
overriding the factory, for example `@ditto.record("json", target="memory://")`.

## When a backend can't be used

ditto never guesses which backend to use, and a registered scheme never falls
back to fsspec:

- **The factory fails to import.** Tests that use the scheme fail with
  `DittoBackendLoadError`, which names the scheme, the package that registered
  it and the original error. Other tests are unaffected.
- **Two packages register the same scheme.** Tests that use the scheme fail
  with `DittoBackendConflictError`, naming both packages. Uninstall one, or
  choose one by setting an override for the scheme.
- **A scheme's factory changes after a test has used one of its targets.**
  Later tests that use the target fail with `DittoBackendChangedError`. Set
  overrides before the first test that uses the scheme.
- **A package registers an invalid scheme, or `file`.** No target can reach
  it, and `ditto doctor` reports it.

[`ditto doctor`](../cli/doctor.md) imports every registered backend and
reports import failures, conflicts and invalid schemes without running any
tests. A factory that changes during a test run only shows up when the tests
run.

## Example: Redis

A complete backend that stores snapshots in Redis, using the
[redis](https://pypi.org/project/redis/) client:

```python
# my_package/backends.py
from collections.abc import Iterator, MutableMapping

import redis

from ditto.backends import PrefixedMapping


class RedisMapping(MutableMapping[str, bytes]):
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
        return (key.decode() for key in self._client.scan_iter())

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __enter__(self) -> "RedisMapping":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._client.close()


def create_redis_backend(uri: str, **storage_options) -> MutableMapping[str, bytes]:
    # redis-py reads host, port and database number from the URI:
    # redis://[user@]host[:port][/db]. ditto refuses a URI with a password.
    client = redis.Redis.from_url(uri, **storage_options)
    return PrefixedMapping(RedisMapping(client), prefix="ditto:")
```

Register it:

```toml
[project.entry-points.ditto_backends]
redis = "my_package.backends:create_redis_backend"
```

Pass the password as a storage option: ditto refuses a target URI that contains
one, because target URIs are recorded in `ditto.lock`.

```python
# conftest.py
import os
import pytest


@pytest.fixture(scope="session")
def ditto_storage_options():
    return {"redis": {"password": os.environ["REDIS_PASSWORD"]}}
```

Then point the tests at it:

```toml
[tool.pytest.ini_options]
ditto_target = "redis://localhost:6379/0"
```

## Runnable examples

The [examples directory](https://github.com/owlowlyowl/pytest-ditto/tree/main/examples)
has self-contained PostgreSQL, Redis and DuckDB backends, each registered from a
`conftest.py`.
