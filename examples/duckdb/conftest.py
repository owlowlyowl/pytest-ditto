from __future__ import annotations

import importlib
import importlib.util
import os
from collections.abc import Callable, Iterator, MutableMapping
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import pytest

from ditto.backends import BACKEND_REGISTRY


BackendFactory = Callable[..., MutableMapping[str, bytes]]


def _default_duckdb_target() -> str:
    database_path = Path(__file__).with_name(".example-snapshots.duckdb").resolve()
    return f"duckdb://{database_path.as_posix()}"


DUCKDB_TARGET = os.getenv("DITTO_DUCKDB_TARGET", _default_duckdb_target())


def _load_duckdb() -> object:
    spec = importlib.util.find_spec("duckdb")
    if spec is None or (
        spec.origin is None and spec.submodule_search_locations is not None
    ):
        pytest.skip("duckdb example needs the duckdb package installed")
    return importlib.import_module("duckdb")


CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS ditto_snapshots (
        key   VARCHAR PRIMARY KEY,
        value BLOB NOT NULL
    )
"""


def _make_duckdb_backend(duckdb_module: object) -> BackendFactory:
    def create_duckdb_backend(
        uri: str, **storage_options: object
    ) -> MutableMapping[str, bytes]:
        connection = duckdb_module.connect(
            _database_from_target(uri),
            **storage_options,
        )
        return DuckDBMapping(connection)

    return create_duckdb_backend


class DuckDBResult(Protocol):
    def fetchone(self) -> tuple[object, ...] | None: ...

    def fetchall(self) -> list[tuple[object, ...]]: ...


class DuckDBConnection(Protocol):
    def execute(
        self,
        query: str,
        parameters: object | None = None,
    ) -> DuckDBResult: ...

    def close(self) -> None: ...


class DuckDBMapping(AbstractContextManager, MutableMapping[str, bytes]):
    """Persist snapshots in a DuckDB table."""

    def __init__(self, conn: DuckDBConnection) -> None:
        self._conn = conn
        self._conn.execute(CREATE_TABLE)

    def __getitem__(self, key: str) -> bytes:
        row = self._conn.execute(
            "SELECT value FROM ditto_snapshots WHERE key = ?",
            [key],
        ).fetchone()
        if row is None:
            raise KeyError(key)
        return row[0]

    def __setitem__(self, key: str, value: bytes) -> None:
        self._conn.execute("DELETE FROM ditto_snapshots WHERE key = ?", [key])
        self._conn.execute(
            "INSERT INTO ditto_snapshots (key, value) VALUES (?, ?)",
            [key, value],
        )

    def __delitem__(self, key: str) -> None:
        if key not in self:
            raise KeyError(key)
        self._conn.execute("DELETE FROM ditto_snapshots WHERE key = ?", [key])

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        row = self._conn.execute(
            "SELECT 1 FROM ditto_snapshots WHERE key = ?",
            [key],
        ).fetchone()
        return row is not None

    def __iter__(self) -> Iterator[str]:
        rows = self._conn.execute(
            "SELECT key FROM ditto_snapshots ORDER BY key"
        ).fetchall()
        return (str(row[0]) for row in rows)

    def __len__(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM ditto_snapshots").fetchone()
        return int(row[0]) if row is not None else 0

    def __enter__(self) -> "DuckDBMapping":
        return self

    def __exit__(self, *args: object) -> None:
        self._conn.close()


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
    """Register the example duckdb:// backend and skip when DuckDB is unavailable."""
    duckdb_module = _load_duckdb()

    try:
        probe = duckdb_module.connect(_database_from_target(DUCKDB_TARGET))
    except Exception as exc:
        pytest.skip(
            "duckdb example needs the duckdb package and a valid "
            f"DITTO_DUCKDB_TARGET ({DUCKDB_TARGET!r}): {exc}"
        )
    else:
        probe.close()

    BACKEND_REGISTRY["duckdb"] = _make_duckdb_backend(duckdb_module)
    yield
    BACKEND_REGISTRY.pop("duckdb", None)
