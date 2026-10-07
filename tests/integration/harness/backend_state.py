from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import TypedDict, cast
from urllib.parse import urlparse

import duckdb
import psycopg2
import redis

from tests.integration.harness.artifacts import write_json_artifact
from tests.integration.harness.workspace import Workspace


class LockEntry(TypedDict):
    nodeid: str
    key: str
    recorder: str


class LockTarget(TypedDict):
    scheme: str
    entries: list[LockEntry]


class LockFile(TypedDict):
    version: int
    targets: dict[str, LockTarget]


def load_lockfile(project: Path) -> LockFile:
    return cast(
        LockFile, json.loads((project / "ditto.lock").read_text(encoding="utf-8"))
    )


def read_backend(
    backend: str,
    project: Path,
    env: Mapping[str, str],
) -> dict[str, bytes]:
    """Every snapshot the backend stores, by storage key, read straight from it."""
    match backend:
        case "local":
            return {
                path.relative_to(project).as_posix(): path.read_bytes()
                for path in _local_snapshot_files(project)
            }
        case "duckdb":
            database = _duckdb_database_from_target(
                _require_env(env, "DITTO_DUCKDB_TARGET")
            )
            with duckdb.connect(database) as connection:
                rows = connection.execute(
                    "SELECT key, value FROM ditto_snapshots ORDER BY key"
                ).fetchall()
            return {str(key): bytes(value) for key, value in rows}
        case "redis":
            client = redis.Redis.from_url(_require_env(env, "DITTO_REDIS_TARGET"))
            try:
                keys = sorted(client.scan_iter(match="ditto:*"))
                stored = {}
                for key in keys:
                    value = client.get(key)
                    if not isinstance(value, bytes):
                        raise RuntimeError(f"Redis snapshot {key!r} has no byte value")
                    stored[key.decode()] = value
                return stored
            finally:
                client.close()
        case "postgres" | "postgresql":
            connection = psycopg2.connect(
                _require_env(env, "DITTO_POSTGRES_TARGET"),
                user=_require_env(env, "DITTO_POSTGRES_USER"),
                password=_require_env(env, "DITTO_POSTGRES_PASSWORD"),
                connect_timeout=3,
            )
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT key, value FROM ditto_snapshots ORDER BY key"
                    )
                    rows = cursor.fetchall()
            finally:
                connection.close()
            return {str(key): bytes(value) for key, value in rows}
        case _:
            raise AssertionError(f"Unsupported backend: {backend}")


def remove_backend_entry(workspace: Workspace, key: str) -> None:
    """Delete the exact physical key supplied by a backend capture."""
    match workspace.backend:
        case "local":
            (workspace.project / key).unlink()
        case "duckdb":
            database = _duckdb_database_from_target(
                workspace.env["DITTO_DUCKDB_TARGET"]
            )
            with duckdb.connect(database) as connection:
                connection.execute("DELETE FROM ditto_snapshots WHERE key = ?", [key])
        case "redis":
            client = redis.Redis.from_url(workspace.env["DITTO_REDIS_TARGET"])
            try:
                if not client.delete(key):
                    raise KeyError(key)
            finally:
                client.close()
        case "postgres":
            connection = psycopg2.connect(
                workspace.env["DITTO_POSTGRES_TARGET"],
                user=workspace.env["DITTO_POSTGRES_USER"],
                password=workspace.env["DITTO_POSTGRES_PASSWORD"],
                connect_timeout=3,
            )
            connection.autocommit = True
            try:
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM ditto_snapshots WHERE key = %s", (key,))
                    if cursor.rowcount != 1:
                        raise KeyError(key)
            finally:
                connection.close()


def capture_backend(workspace: Workspace, label: str) -> dict[str, bytes]:
    """Capture stored bytes as both assertion data and a diagnostic artifact."""
    stored = read_backend(workspace.backend, workspace.project, workspace.env)
    write_json_artifact(
        workspace, label, {key: value.hex() for key, value in stored.items()}
    )
    return stored


def _duckdb_database_from_target(uri: str) -> str:
    parsed = urlparse(uri)
    database = parsed.netloc + parsed.path
    if database == "/:memory:":
        return ":memory:"
    if database.startswith("//"):
        return database[1:]
    return database


def _require_env(env: Mapping[str, str], key: str) -> str:
    value = env.get(key)
    if not value:
        raise AssertionError(f"Missing required environment value: {key}")
    return value


def _local_snapshot_files(project: Path) -> list[Path]:
    return sorted(
        path
        for path in project.rglob("*")
        if path.is_file() and ".standalone-snaps" in path.parts
    )
