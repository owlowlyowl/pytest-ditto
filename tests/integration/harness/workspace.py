from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

type BackendName = Literal["local", "duckdb", "redis", "postgres"]


@dataclass(frozen=True)
class Workspace:
    backend: BackendName
    project: Path
    artifacts: Path
    target_id: str
    scheme: str
    env: Mapping[str, str]


@dataclass(frozen=True)
class RecordedState:
    snapshots: Mapping[str, bytes]
    lock: bytes
