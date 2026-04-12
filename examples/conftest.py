from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session")
def ditto_storage_options() -> dict[str, dict[str, object]]:
    """Return shared storage options for raw URI examples."""
    opts: dict[str, dict[str, object]] = {}

    password = os.getenv("REDIS_PASSWORD")
    if password:
        redis_opts: dict[str, object] = {"password": password}
        username = os.getenv("REDIS_USERNAME")
        if username:
            redis_opts["username"] = username
        opts["redis"] = redis_opts

    return opts
