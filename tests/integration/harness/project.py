from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence

from tests.integration.harness.workspace import Workspace

SUITE = "tests/scenario_suite.py"
ALPHA_NODEID = f"{SUITE}::test_alpha"
BETA_NODEID = f"{SUITE}::test_beta"


def replace_values(workspace: Workspace, values: Sequence[int]) -> None:
    """Set the demo suite's payload values explicitly."""
    suite = workspace.project / SUITE
    before = suite.read_text(encoding="utf-8")
    after, count = re.subn(
        r'"values": \[[^\n]*\]',
        f'"values": {json.dumps(list(values))}',
        before,
    )
    if count != 1 or after == before:
        raise ValueError("Expected one payload definition with different values")
    suite.write_text(after, encoding="utf-8")


def remove_test_beta(workspace: Workspace) -> None:
    """Remove the second test and its decorator from the demo suite."""
    suite = workspace.project / SUITE
    before = suite.read_text(encoding="utf-8")
    definition = before.index("def test_beta")
    decorator = before.rindex("\n@", 0, definition) + 1
    suite.write_text(before[:decorator].rstrip() + "\n", encoding="utf-8")


def snapshot_key_for(stored: Mapping[str, bytes], test_name: str) -> str:
    """Identify one physical storage key by its readable test label."""
    matches = [key for key in stored if re.search(rf"[./]{re.escape(test_name)}@", key)]
    if len(matches) != 1:
        raise ValueError(f"Expected one snapshot for {test_name!r}; found {matches!r}")
    return matches[0]


def logical_storage_key(key: str) -> str:
    """Remove the physical local directory or Redis prefix from a storage key."""
    if "/.standalone-snaps/" in key:
        return key.split("/.standalone-snaps/", 1)[1]
    return key.removeprefix("ditto:")
