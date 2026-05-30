"""Integration tests for the --ditto-introspect pass."""

import json


def test_introspect_pass_enumerates_a_fixture_resolved_generic_backend(
    pytester, tmp_path
):
    """--setup-only --ditto-introspect resolves a fixture-defined generic
    MutableMapping backend and enumerates its stored keys into a manifest,
    without running test bodies."""
    pytester.makeconftest("""
        import pytest
        from collections.abc import MutableMapping
        from ditto.backends import BACKEND_REGISTRY

        # Pre-seeded so the introspect pass has something to enumerate without
        # relying on a prior recording run persisting module state.
        _STORE = {"persist://shared": {"mod/test_seeded@v.json": b'{"x": 1}'}}

        class _DictBackend(MutableMapping):
            def __init__(self, uri, **kwargs):
                self._d = _STORE.setdefault(uri, {})
            def __getitem__(self, k): return self._d[k]
            def __setitem__(self, k, v): self._d[k] = v
            def __delitem__(self, k): del self._d[k]
            def __iter__(self): return iter(self._d)
            def __len__(self): return len(self._d)

        BACKEND_REGISTRY["persist"] = _DictBackend

        @pytest.fixture(scope="session")
        def ditto_target_profiles():
            return {"remote": "persist://shared"}
    """)
    pytester.makepyfile("""
        import ditto

        @ditto.record("json", target_profile="remote")
        def test_inner(snapshot):
            assert snapshot({"x": 1}, key="v") == {"x": 1}
    """)

    manifest_path = tmp_path / "manifest.json"
    result = pytester.runpytest("--setup-only", f"--ditto-introspect={manifest_path}")

    assert result.ret == 0
    backends = json.loads(manifest_path.read_text())  # to_json emits a bare array
    assert len(backends) == 1
    assert backends[0]["location"] == "persist://shared"

    entries = backends[0]["entries"]
    seeded = next(e for e in entries if e["storage_key"] == "mod/test_seeded@v.json")
    # Generic mapping: size measured by a read, no mtime.
    assert seeded["size_bytes"] > 0
    assert seeded["modified"] is None
