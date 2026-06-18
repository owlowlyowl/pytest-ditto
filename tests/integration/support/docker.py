from __future__ import annotations

import shutil
import socket
import subprocess
import time
from contextlib import closing
from dataclasses import dataclass
from uuid import uuid4

import psycopg2
import redis


@dataclass(frozen=True)
class RedisService:
    container_name: str
    host_port: int
    target: str


@dataclass(frozen=True)
class PostgresService:
    container_name: str
    host_port: int
    target: str
    user: str
    password: str
    database: str


def start_redis_service() -> RedisService:
    _require_docker()
    container_name = f"pytest-ditto-int-redis-{uuid4().hex[:8]}"
    host_port = _free_port()
    target = f"redis://127.0.0.1:{host_port}/0"

    try:
        _run(
            [
                "docker",
                "run",
                "--detach",
                "--rm",
                "--name",
                container_name,
                "--publish",
                f"{host_port}:6379",
                "redis:7-alpine",
                "redis-server",
                "--appendonly",
                "yes",
                "--save",
                "",
            ]
        )
        client = redis.Redis.from_url(target)
        try:
            _wait_for_redis(client)
        finally:
            client.close()
    except Exception:
        stop_container(container_name)
        raise

    return RedisService(
        container_name=container_name,
        host_port=host_port,
        target=target,
    )


def start_postgres_service() -> PostgresService:
    _require_docker()
    container_name = f"pytest-ditto-int-postgres-{uuid4().hex[:8]}"
    host_port = _free_port()
    database = "ditto_integration"
    user = "ditto"
    password = "ditto"
    target = f"postgresql://127.0.0.1:{host_port}/{database}"

    try:
        _run(
            [
                "docker",
                "run",
                "--detach",
                "--rm",
                "--name",
                container_name,
                "--publish",
                f"{host_port}:5432",
                "--env",
                f"POSTGRES_DB={database}",
                "--env",
                f"POSTGRES_USER={user}",
                "--env",
                f"POSTGRES_PASSWORD={password}",
                "postgres:16-alpine",
            ]
        )
        _wait_for_postgres(target, user=user, password=password)
    except Exception:
        stop_container(container_name)
        raise

    return PostgresService(
        container_name=container_name,
        host_port=host_port,
        target=target,
        user=user,
        password=password,
        database=database,
    )


def stop_container(container_name: str) -> None:
    if not container_name:
        return
    subprocess.run(
        ["docker", "rm", "--force", container_name],
        capture_output=True,
        text=True,
        check=False,
    )


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(sock.getsockname()[1])


def _require_docker() -> None:
    if shutil.which("docker") is None:
        raise RuntimeError("Docker is required for docker-marked integration tests")


def _run(command: list[str]) -> None:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )


def _wait_for_redis(client: redis.Redis) -> None:
    last_error: Exception | None = None
    for _ in range(60):
        try:
            client.ping()
        except redis.RedisError as exc:
            last_error = exc
            time.sleep(0.25)
        else:
            return
    raise RuntimeError(f"Redis did not become ready: {last_error}")


def _wait_for_postgres(target: str, *, user: str, password: str) -> None:
    last_error: Exception | None = None
    for _ in range(80):
        try:
            connection = psycopg2.connect(
                target,
                user=user,
                password=password,
                connect_timeout=1,
            )
        except psycopg2.OperationalError as exc:
            last_error = exc
            time.sleep(0.25)
        else:
            connection.close()
            return
    raise RuntimeError(f"Postgres did not become ready: {last_error}")
