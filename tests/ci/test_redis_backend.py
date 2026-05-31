"""Integration tests for a registered Redis backend using fakeredis.

Demonstrates wiring a flat key-value store (Redis) as a target-resolved ditto
backend via `redis://` plus a registered factory.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, MutableMapping
from contextlib import AbstractContextManager

import fakeredis
import pytest
import ditto

from ditto.backends import BACKEND_REGISTRY, PrefixedMapping


# ---------------------------------------------------------------------------
# Redis adapter
# ---------------------------------------------------------------------------


class RedisMapping(AbstractContextManager, MutableMapping[str, bytes]):
    """Thin MutableMapping[str, bytes] adapter around a redis client.

    This is example user-land code showing how to connect a Redis client to
    ditto's backend protocol. PrefixedMapping is layered on top to provide
    key-namespace isolation.
    """

    def __init__(self, client: fakeredis.FakeRedis) -> None:
        self._client = client

    def __getitem__(self, key: str) -> bytes:
        val = self._client.get(key)
        if val is None:
            raise KeyError(key)
        return val

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
        # decode_responses=False (default) → scan_iter yields bytes
        return (k.decode() for k in self._client.scan_iter())

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __enter__(self) -> "RedisMapping":
        return self

    def __exit__(self, *args: object) -> None:
        self._client.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def _redis_client() -> fakeredis.FakeRedis:
    """Raw FakeRedis client — exposed so tests can inspect stored keys directly."""
    return fakeredis.FakeRedis()


@pytest.fixture(scope="session", autouse=True)
def _register_redis_backend(_redis_client: fakeredis.FakeRedis):
    def create_redis_backend(uri: str, **kwargs) -> PrefixedMapping:
        return PrefixedMapping(RedisMapping(_redis_client), prefix="ditto:")

    BACKEND_REGISTRY["redis"] = create_redis_backend
    yield
    BACKEND_REGISTRY.pop("redis", None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@ditto.record("pickle", target="redis://localhost:6379/0")
def test_snapshot_round_trips_value_through_redis(snapshot) -> None:
    """Snapshot stores and retrieves a value via the Redis backend."""
    result = snapshot({"answer": 42}, key="data")

    assert result == {"answer": 42}


@ditto.record("pickle", target="redis://localhost:6379/0")
def test_snapshot_keys_use_namespaced_format(_redis_client, snapshot) -> None:
    """Keys stored in Redis use the full module/group@key.ext namespaced form.

    Non-file targets use SnapshotKey.__str__ and therefore include the module
    path for cross-file isolation.
    """
    snapshot(1, key="n")

    raw_keys = [k.decode() for k in _redis_client.keys("*")]
    # Expect something like: ditto:tests/ci/test_redis_backend/test_..._format@n.pkl
    assert any(k.startswith("ditto:") and "/" in k for k in raw_keys), (
        f"expected a namespaced key in Redis, got: {raw_keys}"
    )


@ditto.record("pickle", target="redis://localhost:6379/0")
def test_snapshot_multiple_keys_in_one_test(snapshot) -> None:
    """Multiple snapshot calls with unique keys in one test all round-trip."""
    a = snapshot([1, 2, 3], key="list")
    b = snapshot("hello", key="str")

    assert a == [1, 2, 3]
    assert b == "hello"


def test_dry_run_reports_orphan_redis_key_absent_from_lock(pytester) -> None:
    """A Redis backend key absent from ditto.lock is reported by a dry-run prune.

    Runs two pytester sessions sharing the same FakeRedis instance:
      1. First session writes two keys (alpha, beta) and seeds ditto.lock.
      2. Beta's lock entry is removed, making it an orphan on the backend.
      3. Second session with --ditto-prune-dry-run reports beta as a would-prune
         orphan without deleting it.
    """
    pytester.makeconftest("""
        from collections.abc import Iterator, MutableMapping
        from contextlib import AbstractContextManager
        import ditto
        import fakeredis
        from ditto.backends import BACKEND_REGISTRY, PrefixedMapping

        class RedisMapping(AbstractContextManager, MutableMapping):
            def __init__(self, client):
                self._client = client
            def __getitem__(self, key):
                val = self._client.get(key)
                if val is None:
                    raise KeyError(key)
                return val
            def __setitem__(self, key, value):
                self._client.set(key, value)
            def __delitem__(self, key):
                if not self._client.delete(key):
                    raise KeyError(key)
            def __contains__(self, key):
                return bool(self._client.exists(key)) if isinstance(key, str) else False
            def __iter__(self):
                return (k.decode() for k in self._client.scan_iter())
            def __len__(self):
                return sum(1 for _ in self)
            def __enter__(self):
                return self
            def __exit__(self, *args):
                # Do not close the client here. ditto calls __exit__ via the
                # session ExitStack at the end of each runpytest() call, but
                # _shared_client must survive into the second run so the data
                # written in the first run is still readable. The client's
                # lifetime is managed by the outer test, not by ditto.
                pass

        # Key the FakeServer by a fixed name so the same in-memory store is
        # reused across both in-process pytester runs, even though the conftest
        # module is re-imported between them. A bare FakeRedis() would give each
        # run a fresh, empty server and the orphan would never be seen.
        _server = fakeredis.FakeServer.get_server(
            "ditto-prune-test", version=(7,), server_type="redis"
        )
        _shared_client = fakeredis.FakeRedis(server=_server)

        def create_redis_backend(uri: str, **kwargs):
            return PrefixedMapping(RedisMapping(_shared_client), prefix="ditto:")

        BACKEND_REGISTRY["redis"] = create_redis_backend
    """)
    pytester.makepyfile(
        test_write="""
            import ditto

            @ditto.record("pickle", target="redis://localhost:6379/0")
            def test_write_alpha(snapshot):
                snapshot("alpha-value", key="alpha")

            @ditto.record("pickle", target="redis://localhost:6379/0")
            def test_write_beta(snapshot):
                snapshot("beta-value", key="beta")
        """,
    )

    # First run: create both snapshots and seed ditto.lock.
    result = pytester.runpytest("test_write.py")
    result.assert_outcomes(passed=2)

    # Drop beta's entry from the lock so its backend key becomes an orphan.
    lock_path = pytester.path / "ditto.lock"
    data = json.loads(lock_path.read_text())
    target = next(iter(data["targets"].values()))
    target["entries"] = [
        e for e in target["entries"] if "test_write_beta" not in e["nodeid"]
    ]
    lock_path.write_text(json.dumps(data))

    # Second run with dry-run prune: beta is reported as a would-prune orphan
    # but left in the backend. In-process so the shared FakeRedis client survives.
    result = pytester.runpytest("test_write.py", "--ditto-prune-dry-run")
    result.assert_outcomes(passed=2)
    result.stderr.fnmatch_lines(["*would prune*"])
