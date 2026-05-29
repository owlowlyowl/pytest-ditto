"""Tests for the CLI introspection-pass driver."""

import subprocess
import sys
import textwrap

import pytest

from ditto._cli_introspect import IntrospectError, run_introspect


def test_returns_entries_for_a_file_profile(tmp_path) -> None:
    """run_introspect drives a real pytest pass and returns the enumerated keys,
    with size and mtime recovered for the local file:// backend."""
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        'ditto_target_profile = "local"\n'
        "[tool.pytest-ditto.target_profiles]\n"
        'local = "file://.snaps"\n'
    )
    (tmp_path / "test_thing.py").write_text(
        textwrap.dedent("""
            import ditto

            @ditto.record("json")
            def test_thing(snapshot):
                assert snapshot({"a": 1}, key="v") == {"a": 1}
        """)
    )
    subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=tmp_path, check=True)

    manifest = run_introspect(tmp_path)

    entries = [e for b in manifest for e in b.entries]
    recorded = next(e for e in entries if e.storage_key.endswith("test_thing@v.json"))
    assert recorded.size_bytes > 0
    assert recorded.modified is not None  # local fs reports mtime


def test_returns_empty_manifest_when_no_tests_are_collected(tmp_path) -> None:
    """A path with no tests yields an empty manifest, not an error (pytest exit 5)."""
    manifest = run_introspect(tmp_path)

    assert manifest == []


def test_raises_when_the_pytest_pass_errors(tmp_path) -> None:
    """A collection error raises IntrospectError, never a silent partial manifest."""
    (tmp_path / "test_broken.py").write_text("import does_not_exist\n")

    with pytest.raises(IntrospectError):
        run_introspect(tmp_path)
