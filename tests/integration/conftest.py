from __future__ import annotations

import os
import shutil
from collections.abc import Iterator, Mapping
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import cast
from uuid import uuid4

import pytest

from tests.integration.harness.artifacts import slugify
from tests.integration.harness.backend_state import capture_backend
from tests.integration.harness.cli import run_ditto
from tests.integration.harness.docker import (
    PostgresService,
    RedisService,
    start_postgres_service,
    start_redis_service,
    stop_container,
)
from tests.integration.harness.project import remove_test_beta, snapshot_key_for
from tests.integration.harness.workspace import BackendName, RecordedState, Workspace

collect_ignore = ["projects"]

PROJECTS_ROOT = Path(__file__).parent / "projects"


@pytest.fixture(
    params=[
        pytest.param("local", id="local"),
        pytest.param("duckdb", id="duckdb"),
        pytest.param("redis", id="redis", marks=pytest.mark.docker),
        pytest.param("postgres", id="postgres", marks=pytest.mark.docker),
    ]
)
def backend_name(request: pytest.FixtureRequest) -> BackendName:
    return cast(BackendName, request.param)


@pytest.fixture
def payload_backend(backend_name: BackendName) -> str:
    return "postgresql" if backend_name == "postgres" else backend_name


@pytest.fixture
def project(
    backend_name: BackendName,
    request: pytest.FixtureRequest,
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    scenario = slugify(request.node.name)
    artifacts_dir = os.getenv("DITTO_INTEGRATION_ARTIFACTS_DIR")
    if artifacts_dir:
        root = Path(artifacts_dir).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        scenario_root = root / f"{scenario}-{uuid4().hex[:8]}"
        scenario_root.mkdir()
    else:
        scenario_root = tmp_path_factory.mktemp(scenario)

    project = scenario_root / "project"
    shutil.copytree(PROJECTS_ROOT / f"{backend_name}_project", project)
    (scenario_root / "artifacts").mkdir()
    print(f"[integration:{request.node.name}] project={project}")
    return project


@pytest.fixture
def backend_environment(
    backend_name: BackendName, project: Path, request: pytest.FixtureRequest
) -> Mapping[str, str]:
    match backend_name:
        case "local":
            return {}
        case "duckdb":
            target = project / ".standalone-snapshots.duckdb"
            return {"DITTO_DUCKDB_TARGET": f"duckdb://{target.as_posix()}"}
        case "redis":
            service = cast(RedisService, request.getfixturevalue("redis_service"))
            return {"DITTO_REDIS_TARGET": service.target}
        case "postgres":
            service = cast(PostgresService, request.getfixturevalue("postgres_service"))
            return {
                "DITTO_POSTGRES_TARGET": service.target,
                "DITTO_POSTGRES_USER": service.user,
                "DITTO_POSTGRES_PASSWORD": service.password,
            }


@pytest.fixture
def workspace(
    backend_name: BackendName, project: Path, backend_environment: Mapping[str, str]
) -> Workspace:
    if backend_name == "local":
        target_id, scheme = "tests/.standalone-snaps", "file"
    else:
        target_id = backend_environment[f"DITTO_{backend_name.upper()}_TARGET"]
        scheme = "postgresql" if backend_name == "postgres" else backend_name
    return Workspace(
        backend=backend_name,
        project=project,
        artifacts=project.parent / "artifacts",
        target_id=target_id,
        scheme=scheme,
        env=MappingProxyType(dict(backend_environment)),
    )


@pytest.fixture
def recorded_state(workspace: Workspace) -> RecordedState:
    recorded = run_ditto(workspace, "01-seed", "run")
    assert recorded.returncode == 0
    snapshots = capture_backend(workspace, "01-seeded-backend")
    return RecordedState(
        snapshots=MappingProxyType(snapshots),
        lock=(workspace.project / "ditto.lock").read_bytes(),
    )


@pytest.fixture
def orphaned_state(
    workspace: Workspace, recorded_state: RecordedState
) -> RecordedState:
    remove_test_beta(workspace)
    rebuilt = run_ditto(workspace, "02-lock-without-beta", "lock")
    assert rebuilt.returncode == 0
    return RecordedState(
        snapshots=recorded_state.snapshots,
        lock=(workspace.project / "ditto.lock").read_bytes(),
    )


@pytest.fixture(
    params=[pytest.param((), id="default"), pytest.param(("--live",), id="live")]
)
def inventory_args(request: pytest.FixtureRequest) -> tuple[str, ...]:
    return cast(tuple[str, ...], request.param)


@pytest.fixture
def snapshot_sizes(
    workspace: Workspace, recorded_state: RecordedState, inventory_args: tuple[str, ...]
) -> tuple[str, str]:
    if workspace.scheme != "file" and not inventory_args:
        return "—", "—"
    snapshots = recorded_state.snapshots
    alpha = snapshots[snapshot_key_for(snapshots, "test_alpha")]
    beta = snapshots[snapshot_key_for(snapshots, "test_beta")]
    return f"{len(alpha)} B", f"{len(beta)} B"


@pytest.fixture
def total_size(
    workspace: Workspace, recorded_state: RecordedState, inventory_args: tuple[str, ...]
) -> str:
    if workspace.scheme != "file" and not inventory_args:
        return "—"
    return f"{sum(len(value) for value in recorded_state.snapshots.values())} B"


@pytest.fixture
def snapshot_dates(
    workspace: Workspace, recorded_state: RecordedState
) -> tuple[str, str]:
    if workspace.scheme != "file":
        return "—", "—"
    snapshots = recorded_state.snapshots
    alpha = workspace.project / snapshot_key_for(snapshots, "test_alpha")
    beta = workspace.project / snapshot_key_for(snapshots, "test_beta")
    return (
        datetime.fromtimestamp(alpha.stat().st_mtime).strftime("%Y-%m-%d"),
        datetime.fromtimestamp(beta.stat().st_mtime).strftime("%Y-%m-%d"),
    )


@pytest.fixture
def inventory_location(workspace: Workspace, inventory_args: tuple[str, ...]) -> str:
    if workspace.scheme == "file":
        location = workspace.project / workspace.target_id
        return f"file://{location.as_posix()}" if inventory_args else str(location)
    return workspace.target_id


@pytest.fixture
def redis_service() -> Iterator[RedisService]:
    if shutil.which("docker") is None:
        pytest.skip("Docker is required for docker-marked integration tests")
    service = start_redis_service()
    print(
        f"[integration:redis] container={service.container_name} "
        f"target={service.target}"
    )
    try:
        yield service
    finally:
        stop_container(service.container_name)


@pytest.fixture
def postgres_service() -> Iterator[PostgresService]:
    if shutil.which("docker") is None:
        pytest.skip("Docker is required for docker-marked integration tests")
    service = start_postgres_service()
    print(
        f"[integration:postgres] container={service.container_name} "
        f"target={service.target}"
    )
    try:
        yield service
    finally:
        stop_container(service.container_name)
