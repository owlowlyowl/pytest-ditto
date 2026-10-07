from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

import duckdb
import psycopg2
import redis


def load_lockfile(project: Path) -> dict[str, object]:
    return json.loads((project / "ditto.lock").read_text(encoding="utf-8"))


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
                    assert isinstance(value, bytes), (key, value)
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


def remove_backend_entry(
    backend: str,
    project: Path,
    env: Mapping[str, str],
    needle: str,
) -> str:
    match backend:
        case "local":
            candidates = [
                (path.relative_to(project).as_posix(), path)
                for path in _local_snapshot_files(project)
            ]
            matches = [candidate for candidate in candidates if needle in candidate[0]]
            if not matches:
                raise AssertionError(
                    f"Could not find a local snapshot file containing {needle!r}"
                )
            _, matched_path = matches[0]
            matched_path.unlink()
            return matches[0][0]
        case "duckdb":
            database = _duckdb_database_from_target(
                _require_env(env, "DITTO_DUCKDB_TARGET")
            )
            with duckdb.connect(database) as connection:
                key = _matching_key(
                    [
                        str(row[0])
                        for row in connection.execute(
                            "SELECT key FROM ditto_snapshots ORDER BY key"
                        ).fetchall()
                    ],
                    needle,
                )
                connection.execute("DELETE FROM ditto_snapshots WHERE key = ?", [key])
                return key
        case "redis":
            target = _require_env(env, "DITTO_REDIS_TARGET")
            client = redis.Redis.from_url(target)
            try:
                key = _matching_key(
                    [item.decode() for item in client.scan_iter(match="ditto:*")],
                    needle,
                )
                client.delete(key)
                return key
            finally:
                client.close()
        case "postgres" | "postgresql":
            target = _require_env(env, "DITTO_POSTGRES_TARGET")
            user = _require_env(env, "DITTO_POSTGRES_USER")
            password = _require_env(env, "DITTO_POSTGRES_PASSWORD")
            connection = psycopg2.connect(
                target,
                user=user,
                password=password,
                connect_timeout=3,
            )
            connection.autocommit = True
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT key FROM ditto_snapshots ORDER BY key")
                    key = _matching_key(
                        [str(row[0]) for row in cursor.fetchall()],
                        needle,
                    )
                    cursor.execute(
                        "DELETE FROM ditto_snapshots WHERE key = %s",
                        (key,),
                    )
                return key
            finally:
                connection.close()
        case _:
            raise AssertionError(f"Unsupported backend: {backend}")


def _duckdb_database_from_target(uri: str) -> str:
    parsed = urlparse(uri)
    database = parsed.netloc + parsed.path
    if database == "/:memory:":
        return ":memory:"
    if database.startswith("//"):
        return database[1:]
    return database


def _matching_key(entries: list[str], needle: str) -> str:
    for entry in entries:
        if needle in entry:
            return entry
    raise AssertionError(f"Could not find a backend entry containing {needle!r}")


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
