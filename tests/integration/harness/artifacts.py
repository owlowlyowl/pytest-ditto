from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from pathlib import Path

from tests.integration.harness.workspace import Workspace


def write_text_artifact(workspace: Workspace, name: str, content: str) -> Path:
    path = workspace.artifacts / f"{slugify(name)}.txt"
    path.write_text(content, encoding="utf-8")
    return path


def write_json_artifact(
    workspace: Workspace, name: str, payload: Mapping[str, str]
) -> Path:
    path = workspace.artifacts / f"{slugify(name)}.json"
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8"
    )
    return path


def snapshot_lockfile(workspace: Workspace, label: str) -> None:
    lockfile = workspace.project / "ditto.lock"
    if lockfile.exists():
        shutil.copy2(lockfile, workspace.artifacts / f"{slugify(label)}.ditto.lock")


def slugify(name: str) -> str:
    return "".join(
        char if char.isalnum() or char in {".", "_", "-"} else "-" for char in name
    )
