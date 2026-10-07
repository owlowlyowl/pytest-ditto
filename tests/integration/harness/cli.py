from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass

from tests.integration.harness.artifacts import snapshot_lockfile, write_text_artifact
from tests.integration.harness.workspace import Workspace


@dataclass(frozen=True)
class CliResult:
    label: str
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


def run_ditto(
    workspace: Workspace,
    label: str,
    *args: str,
) -> CliResult:
    ditto = shutil.which("ditto")
    if ditto is None:
        raise AssertionError("The ditto console script was not found on PATH")

    command = [ditto, *args]
    merged_env = os.environ.copy()
    merged_env.update(workspace.env)
    merged_env.setdefault("PYTHONUNBUFFERED", "1")
    # Wide enough that a table row (node id, key, recorder) stays on one line.
    merged_env["COLUMNS"] = "300"
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
    print(
        f"[{workspace.backend}/{workspace.project.parent.name}] cwd={workspace.project}"
    )
    print(f"[{workspace.backend}/{workspace.project.parent.name}] $ {display}")
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(f"[{workspace.backend}/{workspace.project.parent.name}] stderr:")
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n")

    write_text_artifact(
        workspace,
        f"{label}.command",
        f"cwd={workspace.project}\n$ {display}\n",
    )
    write_text_artifact(workspace, f"{label}.stdout", result.stdout)
    write_text_artifact(workspace, f"{label}.stderr", result.stderr)
    snapshot_lockfile(workspace, label)

    return CliResult(
        label=label,
        args=tuple(args),
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
