from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from tests.integration.support.backend_state import (
    load_lockfile,
    read_backend,
    remove_backend_entry,
)

SUITE = "tests/scenario_suite.py"
ALPHA = (f"{SUITE}::test_alpha", "alpha", "json")
BETA = (f"{SUITE}::test_beta", "beta", "json")
VALUES = {
    "local": [1, 2, 3],
    "duckdb": [4, 5, 6],
    "redis": [7, 8, 9],
    "postgres": [10, 11, 12],
}


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
) -> None:
    """Record two snapshots, replay them unchanged, then inventory them."""
    recorded = run_ditto(workspace, "01-run-record", "run", env=env)
    _assert_ok(recorded)
    assert "2 created" in recorded.stderr, recorded.stderr
    stored = _read(workspace, env, "01-backend-after-record")
    assert len(stored) == 2, stored
    _assert_payloads(workspace, stored)
    _assert_lock(workspace, env, (ALPHA, BETA))
    lock = (workspace.project / "ditto.lock").read_bytes()

    replayed = run_ditto(workspace, "02-run-replay", "run", env=env)
    _assert_ok(replayed)
    assert "ditto snapshot report" not in replayed.stderr, replayed.stderr
    assert _read(workspace, env, "02-backend-after-replay") == stored
    assert (workspace.project / "ditto.lock").read_bytes() == lock

    # Local inventory reads files; remote inventory reads the lock by default.
    # The live pass must report byte sizes matching the real backend instead.
    for live in (False, True) if workspace.backend != "local" else (False,):
        flags = ("--live",) if live else ()
        label = "live" if live else "default"
        known_sizes = live or workspace.backend == "local"
        expected_rows = []
        for nodeid, key, recorder in (ALPHA, BETA):
            storage_key = _key_for(stored, f"test_{key}")
            size = f"{len(stored[storage_key])} B" if known_sizes else "—"
            modified = (
                datetime.fromtimestamp(
                    (workspace.project / storage_key).stat().st_mtime
                ).strftime("%Y-%m-%d")
                if workspace.backend == "local"
                else "—"
            )
            expected_rows.append((nodeid, key, recorder, size, modified))

        listed = run_ditto(workspace, f"03-list-{label}", "list", *flags, env=env)
        _assert_ok(listed)
        # Redis SCAN doesn't guarantee ordering; compare all cells and retain
        # duplicates so extra rows still fail the assertion.
        assert sorted(_table_rows(listed.stdout)) == sorted(expected_rows), (
            listed.stdout
        )

        total_size = (
            f"{sum(len(value) for value in stored.values())} B" if known_sizes else "—"
        )
        status = run_ditto(workspace, f"04-status-{label}", "status", *flags, env=env)
        _assert_ok(status)
        lines = [line.strip("│ ") for line in status.stdout.splitlines()]
        assert "Total snapshots  2" in lines, status.stdout
        assert f"Total size       {total_size}" in lines, status.stdout
        assert f"json  2  {total_size}" in lines, status.stdout

        stats = run_ditto(workspace, f"05-stats-{label}", "stats", *flags, env=env)
        _assert_ok(stats)
        target, _ = _target(workspace, env)
        location = (
            str(workspace.project / target) if workspace.backend == "local" else target
        )
        assert _table_rows(stats.stdout) == [
            (location, "2", total_size, "json×2"),
            ("TOTAL", "2", total_size, ""),
        ], stats.stdout

    selected = run_ditto(
        workspace, "06-list-alpha", "list", "--test", ALPHA[0], env=env
    )
    _assert_ok(selected)
    assert [row[:3] for row in _table_rows(selected.stdout)] == [ALPHA]
    assert _read(workspace, env, "06-backend-after-inventory") == stored
    assert (workspace.project / "ditto.lock").read_bytes() == lock


def assert_lock_verify_and_recover(
    workspace: ScenarioWorkspace,
    *,
    env: Mapping[str, str],
) -> None:
    """Verify fails on a snapshot deleted from storage until update restores it."""
    _assert_ok(run_ditto(workspace, "01-run-seed", "run", env=env))
    _assert_ok(run_ditto(workspace, "02-lock-rebuild", "lock", env=env))
    _assert_lock(workspace, env, (ALPHA, BETA))
    stored = _read(workspace, env, "02-backend-seeded")
    _assert_payloads(workspace, stored)
    lock = (workspace.project / "ditto.lock").read_bytes()

    clean_verify = run_ditto(workspace, "03-verify-clean", "verify", env=env)
    _assert_ok(clean_verify)
    assert "ditto verify: no drift in 1 target" in clean_verify.stdout

    removed = remove_backend_entry(
        workspace.backend, workspace.project, env, "test_alpha"
    )
    write_text_artifact(workspace, "04-removed-backend-entry", f"{removed}\n")
    remaining = {key: value for key, value in stored.items() if key != removed}
    assert _read(workspace, env, "04-backend-after-delete") == remaining

    missing_verify = run_ditto(workspace, "05-verify-missing", "verify", env=env)
    assert missing_verify.returncode != 0, missing_verify.stdout
    assert "missing (recorded in lock, absent from backend):" in (
        missing_verify.stdout
    ), missing_verify.stdout
    nodeid, key, _ = ALPHA
    assert _line_with(missing_verify.stdout, nodeid, f"  {key}  "), (
        missing_verify.stdout
    )
    assert _read(workspace, env, "05-backend-after-verify") == remaining
    assert (workspace.project / "ditto.lock").read_bytes() == lock

    _assert_ok(run_ditto(workspace, "06-update-recovery", "update", env=env))
    _assert_ok(run_ditto(workspace, "07-lock-rebuild-recovered", "lock", env=env))
    assert _read(workspace, env, "07-backend-recovered") == stored
    _assert_lock(workspace, env, (ALPHA, BETA))
    _assert_ok(run_ditto(workspace, "08-verify-final", "verify", env=env))


def assert_changed_value_fails_until_updated(
    workspace: ScenarioWorkspace,
    *,
    env: Mapping[str, str],
) -> None:
    """A changed value fails against storage, untouched, until update rewrites it."""
    _assert_ok(run_ditto(workspace, "01-run-record", "run", env=env))
    recorded = _read(workspace, env, "01-backend-recorded")
    _assert_payloads(workspace, recorded)
    _assert_lock(workspace, env, (ALPHA, BETA))
    lock = (workspace.project / "ditto.lock").read_bytes()

    _edit_suite(workspace, lambda text: text.replace('"values": [', '"values": [0, '))
    changed = run_ditto(workspace, "02-run-changed", "run", env=env)
    assert changed.returncode == 1, changed.stdout
    assert "2 failed" in changed.stdout, changed.stdout
    assert f"FAILED {ALPHA[0]} - AssertionError" in changed.stdout, changed.stdout
    assert f"FAILED {BETA[0]} - AssertionError" in changed.stdout, changed.stdout
    assert "ditto snapshot report" not in changed.stderr, changed.stderr
    assert _read(workspace, env, "02-backend-after-failed-run") == recorded
    assert (workspace.project / "ditto.lock").read_bytes() == lock

    updated = run_ditto(workspace, "03-update", "update", env=env)
    _assert_ok(updated)
    assert "2 rewritten" in updated.stderr, updated.stderr
    rewritten = _read(workspace, env, "03-backend-after-update")
    assert rewritten.keys() == recorded.keys()
    assert all(rewritten[key] != recorded[key] for key in recorded), rewritten
    _assert_payloads(workspace, rewritten, changed=True)
    _assert_lock(workspace, env, (ALPHA, BETA))

    replayed = run_ditto(workspace, "04-run-replay", "run", env=env)
    _assert_ok(replayed)
    assert "ditto snapshot report" not in replayed.stderr, replayed.stderr
    assert _read(workspace, env, "04-backend-after-replay") == rewritten


def assert_prune_respects_shared_targets(
    workspace: ScenarioWorkspace,
    *,
    env: Mapping[str, str],
    shared: bool,
) -> None:
    """Prune finds an orphan, but deletes from a shared target only with --shared.

    An orphan is made the way it happens in practice: a test is deleted and
    the lock rebuilt, leaving its stored snapshot behind.
    """
    _assert_ok(run_ditto(workspace, "01-run-seed", "run", env=env))
    stored = _read(workspace, env, "01-backend-seeded")
    _assert_payloads(workspace, stored)
    _assert_lock(workspace, env, (ALPHA, BETA))
    beta_key = _key_for(stored, "test_beta")

    _edit_suite(workspace, _without_test_beta)
    _assert_ok(run_ditto(workspace, "02-lock-without-beta", "lock", env=env))
    _assert_lock(workspace, env, (ALPHA,))
    lock = (workspace.project / "ditto.lock").read_bytes()
    assert _read(workspace, env, "02-backend-after-lock") == stored

    orphan_verify = run_ditto(workspace, "03-verify-orphan", "verify", env=env)
    assert orphan_verify.returncode != 0, orphan_verify.stdout
    assert "orphan (in backend, not in lock):" in orphan_verify.stdout
    assert _storage_name(beta_key) in orphan_verify.stdout, orphan_verify.stdout
    target, _ = _target(workspace, env)
    assert f"  {target}:" in orphan_verify.stdout, orphan_verify.stdout
    assert _read(workspace, env, "03-backend-after-verify") == stored

    check = run_ditto(workspace, "04-prune-check", "prune", "--check", env=env)
    _assert_ok(check)
    row = "shared" if shared else "would prune"
    assert _line_with(check.stderr, f"  {row} ", " 1 "), check.stderr
    assert _storage_name(beta_key) in check.stderr, check.stderr
    assert target in check.stderr, check.stderr
    if shared:
        assert "would prune" not in check.stderr, check.stderr
    assert _read(workspace, env, "04-backend-after-check") == stored

    pruned = run_ditto(workspace, "05-prune", "prune", env=env)
    if shared:
        assert pruned.returncode != 0, pruned.stdout
        assert "not deleting 1 snapshot(s)" in pruned.stdout, pruned.stdout
        assert f"from {target!r}" in pruned.stdout, pruned.stdout
        assert _read(workspace, env, "05-backend-after-refusal") == stored
        assert (workspace.project / "ditto.lock").read_bytes() == lock
        pruned = run_ditto(workspace, "06-prune-shared", "prune", "--shared", env=env)
    _assert_ok(pruned)
    remaining = _read(workspace, env, "06-backend-after-prune")
    assert remaining == {key: value for key, value in stored.items() if key != beta_key}
    assert (workspace.project / "ditto.lock").read_bytes() == lock

    _assert_ok(run_ditto(workspace, "07-verify-final", "verify", env=env))


def _read(
    workspace: ScenarioWorkspace, env: Mapping[str, str], label: str
) -> dict[str, bytes]:
    """The backend's contents, also written as an artifact under `label`."""
    stored = read_backend(workspace.backend, workspace.project, env)
    write_json_artifact(
        workspace, label, {key: value.hex() for key, value in stored.items()}
    )
    return stored


def _target(workspace: ScenarioWorkspace, env: Mapping[str, str]) -> tuple[str, str]:
    if workspace.backend == "local":
        return "tests/.standalone-snaps", "file"
    scheme = "postgresql" if workspace.backend == "postgres" else workspace.backend
    return env[f"DITTO_{workspace.backend.upper()}_TARGET"], scheme


def _assert_lock(
    workspace: ScenarioWorkspace,
    env: Mapping[str, str],
    entries: tuple[tuple[str, str, str], ...],
) -> None:
    target, scheme = _target(workspace, env)
    assert load_lockfile(workspace.project) == {
        "version": 1,
        "targets": {
            target: {
                "scheme": scheme,
                "entries": [
                    {"nodeid": nodeid, "key": key, "recorder": recorder}
                    for nodeid, key, recorder in entries
                ],
            }
        },
    }


def _assert_payloads(
    workspace: ScenarioWorkspace, stored: Mapping[str, bytes], *, changed: bool = False
) -> None:
    assert len(stored) == 2, stored
    values = ([0] if changed else []) + VALUES[workspace.backend]
    backend = "postgresql" if workspace.backend == "postgres" else workspace.backend
    for name in ("alpha", "beta"):
        assert json.loads(stored[_key_for(stored, f"test_{name}")]) == {
            "backend": backend,
            "name": name,
            "values": values,
        }


def _table_rows(output: str) -> list[tuple[str, ...]]:
    """Read cell values, ignoring Rich's borders and column padding."""
    return [
        tuple(cell.strip() for cell in line.split("│")[1:-1])
        for line in output.splitlines()
        if line.startswith("│")
    ]


def _key_for(stored: Mapping[str, bytes], test: str) -> str:
    (key,) = [key for key in stored if re.search(rf"[./]{re.escape(test)}@", key)]
    return key


def _storage_name(key: str) -> str:
    """The complete logical key without Redis's prefix or the local directory."""
    if "/.standalone-snaps/" in key:
        return key.split("/.standalone-snaps/", 1)[1]
    return key.removeprefix("ditto:")


def _line_with(output: str, *fragments: str) -> bool:
    return any(all(f in line for f in fragments) for line in output.splitlines())


def _edit_suite(workspace: ScenarioWorkspace, change: Callable[[str], str]) -> None:
    suite = workspace.project / SUITE
    before = suite.read_text(encoding="utf-8")
    after = change(before)
    assert after != before, "the suite edit changed nothing"
    suite.write_text(after, encoding="utf-8")


def _without_test_beta(text: str) -> str:
    """The suite with `test_beta` and its decorator removed."""
    definition = text.index("def test_beta")
    decorator = text.rindex("\n@", 0, definition) + 1
    return text[:decorator].rstrip() + "\n"


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
    # Wide enough that a table row (node id, key, recorder) stays on one line.
    merged_env["COLUMNS"] = "200"
    merged_env["NO_COLOR"] = "1"

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
