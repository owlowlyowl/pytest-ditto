from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from uuid import uuid4

import pytest

from tests.integration.support.cli import ScenarioWorkspace
from tests.integration.support.docker import (
    PostgresService,
    RedisService,
    start_postgres_service,
    start_redis_service,
    stop_container,
)

collect_ignore = ["projects"]

PROJECTS_ROOT = Path(__file__).parent / "projects"


def _scenario_root(
    tmp_path_factory: pytest.TempPathFactory,
    backend: str,
    scenario: str,
) -> Path:
    artifacts_dir = os.getenv("DITTO_INTEGRATION_ARTIFACTS_DIR")
    if artifacts_dir:
        root = Path(artifacts_dir).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        scenario_root = root / f"{backend}-{scenario}-{uuid4().hex[:8]}"
        scenario_root.mkdir(parents=True, exist_ok=False)
        return scenario_root

    return tmp_path_factory.mktemp(f"{backend}-{scenario}")


@pytest.fixture
def project_workspace(
    tmp_path_factory: pytest.TempPathFactory,
) -> Callable[[str, str], ScenarioWorkspace]:
    def build(backend: str, scenario: str) -> ScenarioWorkspace:
        scenario_root = _scenario_root(tmp_path_factory, backend, scenario)
        project = scenario_root / "project"
        artifacts = scenario_root / "artifacts"
        shutil.copytree(PROJECTS_ROOT / f"{backend}_project", project)
        artifacts.mkdir(parents=True, exist_ok=True)
        print(f"[integration:{backend}/{scenario}] project={project}")
        print(f"[integration:{backend}/{scenario}] artifacts={artifacts}")
        return ScenarioWorkspace(
            backend=backend,
            scenario=scenario,
            root=scenario_root,
            project=project,
            artifacts=artifacts,
        )

    return build


@pytest.fixture
def redis_service() -> Iterator[RedisService]:
    try:
        service = start_redis_service()
    except RuntimeError as exc:
        pytest.skip(str(exc))

    print(
        f"[integration:redis] container={service.container_name} target={service.target}"
    )
    try:
        yield service
    finally:
        stop_container(service.container_name)


@pytest.fixture
def postgres_service() -> Iterator[PostgresService]:
    try:
        service = start_postgres_service()
    except RuntimeError as exc:
        pytest.skip(str(exc))

    print(
        "[integration:postgresql] "
        f"container={service.container_name} target={service.target}"
    )
    try:
        yield service
    finally:
        stop_container(service.container_name)

