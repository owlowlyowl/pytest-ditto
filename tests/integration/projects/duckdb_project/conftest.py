from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from contextlib import AbstractContextManager
from urllib.parse import urlparse

import duckdb
import pytest

from ditto.backends import BACKEND_REGISTRY

CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS ditto_snapshots (
        key   VARCHAR PRIMARY KEY,
        value BLOB NOT NULL
    )
"""


class DuckDBMapping(AbstractContextManager, MutableMapping[str, bytes]):
    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._connection = connection
        self._connection.execute(CREATE_TABLE)

    def __getitem__(self, key: str) -> bytes:
        row = self._connection.execute(
            "SELECT value FROM ditto_snapshots WHERE key = ?",
            [key],
        ).fetchone()
        if row is None:
            raise KeyError(key)
        return bytes(row[0])

    def __setitem__(self, key: str, value: bytes) -> None:
        self._connection.execute("DELETE FROM ditto_snapshots WHERE key = ?", [key])
        self._connection.execute(
            "INSERT INTO ditto_snapshots (key, value) VALUES (?, ?)",
            [key, value],
        )

    def __delitem__(self, key: str) -> None:
        if key not in self:
            raise KeyError(key)
        self._connection.execute("DELETE FROM ditto_snapshots WHERE key = ?", [key])

    def __iter__(self) -> Iterator[str]:
        rows = self._connection.execute(
            "SELECT key FROM ditto_snapshots ORDER BY key"
        ).fetchall()
        return (str(row[0]) for row in rows)

    def __len__(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) FROM ditto_snapshots").fetchone()
        return int(row[0]) if row is not None else 0

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        row = self._connection.execute(
            "SELECT 1 FROM ditto_snapshots WHERE key = ?",
            [key],
        ).fetchone()
        return row is not None

    def __enter__(self) -> DuckDBMapping:
        return self

    def __exit__(self, *args: object) -> None:
        self._connection.close()


def _database_from_target(uri: str) -> str:
    parsed = urlparse(uri)
    database = parsed.netloc + parsed.path
    if database == "/:memory:":
        return ":memory:"
    if database.startswith("//"):
        return database[1:]
    return database

@pytest.fixture(scope="session", autouse=True)
def _register_duckdb_backend() -> Iterator[None]:
    def create_duckdb_backend(uri: str, **storage_options: object) -> MutableMapping[str, bytes]:
        connection = duckdb.connect(
            _database_from_target(uri),
            **storage_options,
        )
        return DuckDBMapping(connection)

    BACKEND_REGISTRY["duckdb"] = create_duckdb_backend
    yield
    BACKEND_REGISTRY.pop("duckdb", None)
