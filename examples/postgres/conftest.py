from __future__ import annotations

import importlib
import importlib.util
import os
import time
from collections.abc import Callable, Iterator, MutableMapping
from contextlib import AbstractContextManager

import pytest

from ditto.backends import BACKEND_REGISTRY


POSTGRES_TARGET = os.getenv(
    "DITTO_POSTGRES_TARGET",
    "postgresql://localhost:5433/ditto_examples",
)
POSTGRES_USER = os.getenv("DITTO_POSTGRES_USER", os.getenv("PGUSER", "ditto"))
POSTGRES_PASSWORD = os.getenv(
    "DITTO_POSTGRES_PASSWORD",
    os.getenv("PGPASSWORD", "ditto"),
)
BackendFactory = Callable[..., MutableMapping[str, bytes]]
CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS ditto_snapshots (
        key   TEXT PRIMARY KEY,
        value BYTEA NOT NULL
    )
"""


def _load_psycopg2() -> object:
    spec = importlib.util.find_spec("psycopg2")
    if spec is None or (
        spec.origin is None and spec.submodule_search_locations is not None
    ):
        pytest.skip("postgres example needs the psycopg2 package installed")
    return importlib.import_module("psycopg2")


def _profile_storage_options() -> dict[str, object]:
    return {
        "user": POSTGRES_USER,
        "password": POSTGRES_PASSWORD,
        "connect_timeout": 3,
    }


def _make_postgres_backend(psycopg2_module: object) -> BackendFactory:
    def create_postgres_backend(
        uri: str, **storage_options: object
    ) -> MutableMapping[str, bytes]:
        connection = psycopg2_module.connect(uri, **storage_options)
        connection.autocommit = True
        return PostgresMapping(connection)

    return create_postgres_backend


class PostgresMapping(AbstractContextManager, MutableMapping[str, bytes]):
    """Persist snapshots in a PostgreSQL table."""

    def __init__(self, connection: object) -> None:
        self._connection = connection
        with self._connection.cursor() as cursor:
            cursor.execute(CREATE_TABLE)

    def __getitem__(self, key: str) -> bytes:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT value FROM ditto_snapshots WHERE key = %s",
                (key,),
            )
            row = cursor.fetchone()
        if row is None:
            raise KeyError(key)

        value = row[0]
        if isinstance(value, memoryview):
            return value.tobytes()
        return bytes(value)

    def __setitem__(self, key: str, value: bytes) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO ditto_snapshots (key, value)
                VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value
                """,
                (key, value),
            )

    def __delitem__(self, key: str) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM ditto_snapshots WHERE key = %s RETURNING key",
                (key,),
            )
            row = cursor.fetchone()
        if row is None:
            raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM ditto_snapshots WHERE key = %s",
                (key,),
            )
            row = cursor.fetchone()
        return row is not None

    def __iter__(self) -> Iterator[str]:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT key FROM ditto_snapshots ORDER BY key")
            rows = cursor.fetchall()
        return (str(row[0]) for row in rows)

    def __len__(self) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM ditto_snapshots")
            row = cursor.fetchone()
        return int(row[0]) if row is not None else 0

    def __enter__(self) -> "PostgresMapping":
        return self

    def __exit__(self, *args: object) -> None:
        self._connection.close()


def _probe_postgres(psycopg2_module: object) -> None:
    last_error: Exception | None = None

    for _ in range(20):
        connection = None
        try:
            connection = psycopg2_module.connect(
                POSTGRES_TARGET,
                **_profile_storage_options(),
            )
        except psycopg2_module.OperationalError as exc:
            last_error = exc
            time.sleep(0.25)
            continue
        else:
            connection.close()
            return

    pytest.skip(
        "postgres example needs the examples Docker container running at "
        f"{POSTGRES_TARGET!r}: {last_error}"
    )


@pytest.fixture(scope="session")
def ditto_target_profiles() -> dict[str, dict[str, object]]:
    """Return the named target profile used by the Postgres dataframe example."""
    return {
        "postgres_frames": {
            "uri": POSTGRES_TARGET,
            "storage_options": _profile_storage_options(),
        }
    }


@pytest.fixture(scope="session", autouse=True)
def _register_postgres_backend() -> Iterator[None]:
    """Register the example postgresql:// backend.

    Skip the example when the Postgres runtime is unavailable.
    """
    psycopg2_module = _load_psycopg2()
    _probe_postgres(psycopg2_module)

    BACKEND_REGISTRY["postgresql"] = _make_postgres_backend(psycopg2_module)
    yield
    BACKEND_REGISTRY.pop("postgresql", None)
