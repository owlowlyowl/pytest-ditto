from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.docker
def test_docker_is_available() -> None:
    """The full integration suite requires Docker rather than skipping silently."""
    assert shutil.which("docker") is not None, (
        "Docker is required for the full integration suite. "
        "Use test-integration-local to run without Docker."
    )
