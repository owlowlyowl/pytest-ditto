from __future__ import annotations

import os
from collections.abc import Iterator, MutableMapping
from contextlib import AbstractContextManager

import psycopg2
import pytest

from ditto.backends import BACKEND_REGISTRY

CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS ditto_snapshots (
        key   TEXT PRIMARY KEY,
        value BYTEA NOT NULL
    )
"""

POSTGRES_USER = os.getenv("DITTO_POSTGRES_USER", "ditto")
POSTGRES_PASSWORD = os.getenv("DITTO_POSTGRES_PASSWORD", "ditto")


class PostgresMapping(AbstractContextManager, MutableMapping[str, bytes]):
    def __init__(self, connection: psycopg2.extensions.connection) -> None:
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

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM ditto_snapshots WHERE key = %s", (key,))
            row = cursor.fetchone()
        return row is not None

    def __enter__(self) -> PostgresMapping:
        return self

    def __exit__(self, *args: object) -> None:
        self._connection.close()


@pytest.fixture(scope="session", autouse=True)
def _register_postgresql_backend() -> Iterator[None]:
    def create_postgresql_backend(
        uri: str, **storage_options: object
    ) -> MutableMapping[str, bytes]:
        connection = psycopg2.connect(
            uri,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            **storage_options,
        )
        connection.autocommit = True
        return PostgresMapping(connection)

    BACKEND_REGISTRY["postgresql"] = create_postgresql_backend
    yield
    BACKEND_REGISTRY.pop("postgresql", None)
