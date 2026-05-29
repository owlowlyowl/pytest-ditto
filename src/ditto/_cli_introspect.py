"""Drive the in-pytest introspection pass and load its manifest."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from ditto._manifest import Manifest, from_json

# pytest's exit code when collection finds no tests — an empty inventory, not a
# failure. https://docs.pytest.org/en/stable/reference/exit-codes.html
_PYTEST_NO_TESTS_COLLECTED = 5


class IntrospectError(RuntimeError):
    """Raised when the pytest introspection pass fails to produce a usable manifest."""


def run_introspect(path: Path) -> Manifest:
    """Run `pytest <path> --setup-only --ditto-introspect=<tmp>` and return the
    manifest it writes.

    Raises IntrospectError on any error exit (collection/import/setup failure) so
    an incomplete pass is never mistaken for an empty or complete inventory. A
    "no tests collected" exit (5) is treated as a legitimately empty inventory.
    """
    with tempfile.TemporaryDirectory() as tmp:
        manifest_path = Path(tmp) / "manifest.json"
        completed = subprocess.run(
            [
                sys.executable, "-m", "pytest", str(path), "--setup-only", "-q",
                f"--ditto-introspect={manifest_path}",
            ],
            capture_output=True,
            text=True,
        )
        ok = completed.returncode in (0, _PYTEST_NO_TESTS_COLLECTED)
        if not ok or not manifest_path.exists():
            raise IntrospectError(
                "ditto introspection pass failed "
                f"(pytest exit {completed.returncode}):\n"
                f"{completed.stdout}\n{completed.stderr}"
            )
        return from_json(manifest_path.read_text())
