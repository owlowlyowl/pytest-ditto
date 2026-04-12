import pytest


def test_target_profile_mark_resolves_to_configured_uri(pytester) -> None:
    """target_profile= in a mark expands to the URI from the fixture profile table."""
    pytester.makeconftest("""
        import pytest

        @pytest.fixture(scope="session")
        def ditto_target_profiles():
            return {"golden": "memory://golden"}
    """)
    pytester.makepyfile("""
        import ditto

        @ditto.record("json", target_profile="golden")
        def test_inner(snapshot):
            actual = snapshot.target

            expected = "memory://golden"
            assert actual == expected
            assert snapshot({"x": 1}, key="x") == {"x": 1}
    """)

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)


def test_ditto_target_profile_ini_is_used_when_mark_has_no_target(pytester) -> None:
    """ditto_target_profile ini selects the default profile when the mark carries no target."""
    pytester.makeconftest("""
        import pytest

        @pytest.fixture(scope="session")
        def ditto_target_profiles():
            return {"golden": "memory://golden"}
    """)
    pytester.makeini("""
        [pytest]
        ditto_target_profile = golden
    """)
    pytester.makepyfile("""
        import ditto

        @ditto.record("json")
        def test_inner(snapshot):
            actual = snapshot.target

            expected = "memory://golden"
            assert actual == expected
            assert snapshot({"x": 1}, key="x") == {"x": 1}
    """)

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)


def test_mark_target_uri_takes_precedence_over_ditto_target_profile_ini(pytester) -> None:
    """A mark-level target= URI wins over a ditto_target_profile ini default."""
    pytester.makeconftest("""
        import pytest

        @pytest.fixture(scope="session")
        def ditto_target_profiles():
            return {"golden": "memory://golden"}
    """)
    pytester.makeini("""
        [pytest]
        ditto_target_profile = golden
    """)
    pytester.makepyfile("""
        import ditto

        @ditto.record("json", target="memory://override")
        def test_inner(snapshot):
            actual = snapshot.target

            expected = "memory://override"
            assert actual == expected
            assert snapshot({"x": 1}, key="x") == {"x": 1}
    """)

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)


def test_profile_storage_options_are_not_merged_with_ditto_storage_options(pytester) -> None:
    """Profile-based targets use only their own storage_options; ditto_storage_options is ignored."""
    pytester.makeconftest("""
        import pytest
        from ditto.backends import BACKEND_REGISTRY
        from collections.abc import MutableMapping

        received_kwargs = {}

        class _CapturingBackend(MutableMapping):
            def __init__(self, uri, **kwargs):
                received_kwargs.update(kwargs)
                self._d = {}
            def __getitem__(self, k): return self._d[k]
            def __setitem__(self, k, v): self._d[k] = v
            def __delitem__(self, k): del self._d[k]
            def __iter__(self): return iter(self._d)
            def __len__(self): return len(self._d)

        BACKEND_REGISTRY["capture"] = _CapturingBackend

        @pytest.fixture(scope="session")
        def ditto_target_profiles():
            return {
                "profiled": {
                    "uri": "capture://bucket",
                    "storage_options": {"profile_key": "pval"},
                }
            }

        @pytest.fixture(scope="session")
        def ditto_storage_options():
            return {"capture": {"scheme_key": "sval"}}

        @pytest.fixture
        def captured():
            return received_kwargs
    """)
    pytester.makepyfile("""
        import ditto

        @ditto.record("json", target_profile="profiled")
        def test_inner(snapshot, captured):
            snapshot({"x": 1}, key="x")
            assert "profile_key" in captured
            assert "scheme_key" not in captured
    """)

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)


def test_raises_when_target_and_target_profile_are_both_set(pytester) -> None:
    """target= and target_profile= on the same mark raises an error."""
    pytester.makeconftest("""
        import pytest

        @pytest.fixture(scope="session")
        def ditto_target_profiles():
            return {"golden": "memory://golden"}
    """)
    pytester.makepyfile("""
        import ditto

        @ditto.record("json", target="memory://x", target_profile="golden")
        def test_inner(snapshot):
            snapshot(1, key="k")
    """)

    result = pytester.runpytest()

    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*Use either target= or target_profile=, not both*"])


def test_raises_when_ditto_target_and_ditto_target_profile_are_both_configured(pytester) -> None:
    """ditto_target and ditto_target_profile in config together raises at configure time."""
    pytester.makeini("""
        [pytest]
        ditto_target = memory://x
        ditto_target_profile = golden
    """)
    pytester.makepyfile("""
        def test_inner(snapshot):
            snapshot(1, key="k")
    """)

    result = pytester.runpytest()

    assert result.ret != 0
    result.stderr.fnmatch_lines(["*Use either ditto_target or ditto_target_profile, not both*"])


def test_raises_when_duplicate_profile_name_exists_in_fixture_and_static_config(pytester) -> None:
    """A profile name defined in both the fixture and pyproject.toml raises an error."""
    pytester.makeconftest("""
        import pytest

        @pytest.fixture(scope="session")
        def ditto_target_profiles():
            return {"golden": "memory://fixture-golden"}
    """)
    pytester.makepyprojecttoml("""
        [tool.pytest-ditto.target_profiles]
        golden = "memory://static-golden"
    """)
    pytester.makepyfile("""
        import ditto

        @ditto.record("json", target_profile="golden")
        def test_inner(snapshot):
            snapshot(1, key="k")
    """)

    result = pytester.runpytest()

    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*Duplicate ditto target profile*golden*"])


def test_raises_when_unknown_profile_name_is_requested(pytester) -> None:
    """Requesting a profile name not in the table raises a clear error."""
    pytester.makeconftest("""
        import pytest

        @pytest.fixture(scope="session")
        def ditto_target_profiles():
            return {"local_alt": "file://.snapshots"}
    """)
    pytester.makepyfile("""
        import ditto

        @ditto.record("json", target_profile="kirby")
        def test_inner(snapshot):
            snapshot(1, key="k")
    """)

    result = pytester.runpytest()

    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*Unknown ditto target profile 'kirby'*"])


def test_raises_when_profile_fixture_dependency_is_missing(pytester) -> None:
    """A broken ditto_target_profiles fixture dependency fails loudly instead of falling back."""
    pytester.makeconftest("""
        import pytest

        @pytest.fixture(scope="session")
        def ditto_target_profiles(nonexistent_dep):
            return {"golden": "memory://golden"}
    """)
    pytester.makepyfile("""
        import ditto

        @ditto.record("json", target_profile="golden")
        def test_inner(snapshot):
            snapshot(1, key="k")
    """)

    result = pytester.runpytest()

    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*fixture 'nonexistent_dep' not found*"])


def test_two_profiles_with_same_uri_and_options_share_a_backend(pytester) -> None:
    """Two profiles that resolve to identical URI and options share one backend instance."""
    pytester.makeconftest("""
        import pytest
        from ditto.backends import BACKEND_REGISTRY

        _instances = []

        class _TrackingBackend(dict):
            def __init__(self, uri, **kwargs):
                _instances.append(self)
                super().__init__()

        BACKEND_REGISTRY["track"] = _TrackingBackend

        @pytest.fixture(scope="session")
        def ditto_target_profiles():
            return {
                "alias_a": {"uri": "track://shared", "storage_options": {}},
                "alias_b": {"uri": "track://shared", "storage_options": {}},
            }

        @pytest.fixture
        def instance_count():
            return _instances
    """)
    pytester.makepyfile("""
        import ditto

        @ditto.record("json", target_profile="alias_a")
        def test_a(snapshot, instance_count):
            snapshot(1, key="v")
            assert len(instance_count) == 1

        @ditto.record("json", target_profile="alias_b")
        def test_b(snapshot, instance_count):
            snapshot(2, key="v")
            assert len(instance_count) == 1
    """)

    result = pytester.runpytest("-v")

    result.assert_outcomes(passed=2)


def test_two_profiles_with_same_uri_but_different_options_use_separate_backends(pytester) -> None:
    """Two profiles with the same URI but different storage_options use distinct backends."""
    pytester.makeconftest("""
        import pytest
        from ditto.backends import BACKEND_REGISTRY

        _instances = []

        class _TrackingBackend(dict):
            def __init__(self, uri, **kwargs):
                _instances.append(self)
                super().__init__()

        BACKEND_REGISTRY["track2"] = _TrackingBackend

        @pytest.fixture(scope="session")
        def ditto_target_profiles():
            return {
                "creds_a": {"uri": "track2://shared", "storage_options": {"key": "A"}},
                "creds_b": {"uri": "track2://shared", "storage_options": {"key": "B"}},
            }

        @pytest.fixture
        def instance_count():
            return _instances
    """)
    pytester.makepyfile("""
        import ditto

        @ditto.record("json", target_profile="creds_a")
        def test_a(snapshot, instance_count):
            snapshot(1, key="v")

        @ditto.record("json", target_profile="creds_b")
        def test_b(snapshot, instance_count):
            snapshot(2, key="v")
            assert len(instance_count) == 2
    """)

    result = pytester.runpytest("-v")

    result.assert_outcomes(passed=2)


def test_profile_with_file_uri_resolves_relative_to_test_file(pytester) -> None:
    """A profile with a relative file:// URI resolves relative to the test file's directory."""
    pytester.makeconftest("""
        import pytest

        @pytest.fixture(scope="session")
        def ditto_target_profiles():
            return {"local_custom": "file://.custom"}
    """)
    pytester.makepyfile("""
        import ditto

        @ditto.record("json", target_profile="local_custom")
        def test_inner(snapshot):
            actual = snapshot.target

            assert actual.endswith("/.custom")
            assert snapshot({"x": 1}, key="x") == {"x": 1}
    """)

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)
    assert (pytester.path / ".custom").is_dir()


def test_static_pyproject_profiles_are_used_when_fixture_is_absent(pytester) -> None:
    """Profiles defined only in pyproject.toml are resolved without a fixture."""
    pytester.makepyprojecttoml("""
        [tool.pytest-ditto.target_profiles]
        memory_shared = "memory://static-shared"
    """)
    pytester.makepyfile("""
        import ditto

        @ditto.record("json", target_profile="memory_shared")
        def test_inner(snapshot):
            actual = snapshot.target

            expected = "memory://static-shared"
            assert actual == expected
            assert snapshot({"x": 1}, key="x") == {"x": 1}
    """)

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)
