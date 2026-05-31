from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from collections.abc import Mapping

from tests.integration.support.backend_state import (
    dump_backend_entries,
    load_lock_nodeids,
    remove_backend_entry,
)


@dataclass(frozen=True)
class ScenarioWorkspace:
    backend: str
    scenario: str
    root: Path
    project: Path
    artifacts: Path


@dataclass(frozen=True)
class CliResult:
    label: str
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


def assert_record_replay_inventory(
    workspace: ScenarioWorkspace,
    *,
    env: Mapping[str, str],
    list_tokens: tuple[str, ...],
    status_tokens: tuple[str, ...],
    stats_tokens: tuple[str, ...],
) -> None:
    recorded = run_ditto(workspace, "01-run-record", "run", env=env)
    _assert_ok(recorded)

    replayed = run_ditto(workspace, "02-run-replay", "run", env=env)
    _assert_ok(replayed)

    entries = dump_backend_entries(
        workspace.backend,
        workspace.project,
        env,
        workspace.artifacts / "02-backend-entries.txt",
    )
    assert len(entries) == 2, entries
    assert any("test_alpha" in entry for entry in entries), entries
    assert any("test_beta" in entry for entry in entries), entries

    nodeids = load_lock_nodeids(workspace.project)
    write_json_artifact(workspace, "02-lock-nodeids", nodeids)
    assert len(nodeids) == 2, nodeids
    assert any("test_alpha" in nodeid for nodeid in nodeids), nodeids
    assert any("test_beta" in nodeid for nodeid in nodeids), nodeids

    listed = run_ditto(workspace, "03-list", "list", env=env)
    _assert_ok(listed)
    for token in list_tokens:
        assert token in listed.stdout, listed.stdout

    status = run_ditto(workspace, "04-status", "status", env=env)
    _assert_ok(status)
    for token in status_tokens:
        assert token in status.stdout, status.stdout

    stats = run_ditto(workspace, "05-stats", "stats", env=env)
    _assert_ok(stats)
    for token in stats_tokens:
        assert token in stats.stdout, stats.stdout


def assert_lock_verify_and_recover(
    workspace: ScenarioWorkspace,
    *,
    env: Mapping[str, str],
    missing_fragment: str,
) -> None:
    seeded = run_ditto(workspace, "01-run-seed", "run", env=env)
    _assert_ok(seeded)

    nodeids = load_lock_nodeids(workspace.project)
    write_json_artifact(workspace, "01-lock-nodeids", nodeids)
    assert len(nodeids) == 2, nodeids

    rebuilt = run_ditto(workspace, "02-lock-rebuild", "lock", env=env)
    _assert_ok(rebuilt)

    clean_verify = run_ditto(workspace, "03-verify-clean", "verify", env=env)
    _assert_ok(clean_verify)

    removed = remove_backend_entry(
        workspace.backend,
        workspace.project,
        env,
        missing_fragment,
    )
    write_text_artifact(workspace, "04-removed-backend-entry", f"{removed}\n")
    dump_backend_entries(
        workspace.backend,
        workspace.project,
        env,
        workspace.artifacts / "04-backend-entries-after-delete.txt",
    )

    missing_verify = run_ditto(workspace, "05-verify-missing", "verify", env=env)
    assert missing_verify.returncode != 0, missing_verify.stdout
    combined = f"{missing_verify.stdout}\n{missing_verify.stderr}".lower()
    assert "missing" in combined, combined
    assert missing_fragment in combined, combined

    recovered = run_ditto(workspace, "06-update-recovery", "update", env=env)
    _assert_ok(recovered)

    re_locked = run_ditto(workspace, "07-lock-rebuild-recovered", "lock", env=env)
    _assert_ok(re_locked)

    recovered_entries = dump_backend_entries(
        workspace.backend,
        workspace.project,
        env,
        workspace.artifacts / "07-backend-entries-recovered.txt",
    )
    assert any(missing_fragment in entry for entry in recovered_entries), recovered_entries

    final_verify = run_ditto(workspace, "08-verify-final", "verify", env=env)
    _assert_ok(final_verify)


def run_ditto(
    workspace: ScenarioWorkspace,
    label: str,
    *args: str,
    env: Mapping[str, str],
) -> CliResult:
    ditto = shutil.which("ditto")
    if ditto is None:
        raise AssertionError("The ditto console script was not found on PATH")

    command = [ditto, *args]
    merged_env = os.environ.copy()
    merged_env.update(env)
    merged_env.setdefault("PYTHONUNBUFFERED", "1")

    result = subprocess.run(
        command,
        cwd=workspace.project,
        env=merged_env,
        capture_output=True,
        text=True,
        check=False,
    )

    display = shlex.join(command)
    print(f"[{workspace.backend}/{workspace.scenario}] cwd={workspace.project}")
    print(f"[{workspace.backend}/{workspace.scenario}] $ {display}")
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(f"[{workspace.backend}/{workspace.scenario}] stderr:")
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n")

    write_text_artifact(
        workspace,
        f"{label}.command",
        f"cwd={workspace.project}\n$ {display}\n",
    )
    write_text_artifact(workspace, f"{label}.stdout", result.stdout)
    write_text_artifact(workspace, f"{label}.stderr", result.stderr)
    _snapshot_lockfile(workspace, label)

    return CliResult(
        label=label,
        args=tuple(args),
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def write_text_artifact(
    workspace: ScenarioWorkspace,
    name: str,
    content: str,
) -> Path:
    path = workspace.artifacts / f"{_slugify(name)}.txt"
    path.write_text(content, encoding="utf-8")
    return path


def write_json_artifact(
    workspace: ScenarioWorkspace,
    name: str,
    payload: Any,
) -> Path:
    path = workspace.artifacts / f"{_slugify(name)}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _snapshot_lockfile(workspace: ScenarioWorkspace, label: str) -> None:
    lockfile = workspace.project / "ditto.lock"
    if lockfile.exists():
        shutil.copy2(lockfile, workspace.artifacts / f"{_slugify(label)}.ditto.lock")


def _assert_ok(result: CliResult) -> None:
    assert result.returncode == 0, (
        f"Command failed: {' '.join(result.args)}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def _slugify(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {".", "_", "-"} else "-" for ch in name)
