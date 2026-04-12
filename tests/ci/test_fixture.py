import pytest

from ditto import Snapshot


def test_injects_snapshot_instance_into_test(snapshot) -> None:
    """The snapshot fixture injects a Snapshot instance into the test."""
    assert isinstance(snapshot, Snapshot)


def test_raises_when_key_is_not_provided(snapshot) -> None:
    """snapshot raises TypeError when called without the required key argument."""
    with pytest.raises(TypeError) as excinfo:
        snapshot(1)
    assert excinfo.match(
        r"^Snapshot.__call__().*missing 1 required positional argument: 'key'"
    )


def test_returns_value_on_first_call(pytester) -> None:
    """snapshot returns the value passed to it when no snapshot file exists yet."""
    pytester.makepyfile("""
        def test_inner(snapshot):
            actual = snapshot("write-value", key="write")
            assert actual == "write-value"
    """)

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)


def test_returns_stored_value_on_subsequent_calls(snapshot) -> None:
    """snapshot returns the stored value, not the argument, when the file exists."""
    key = "read"

    # tests/ci/.ditto/test_returns_stored_value_on_subsequent_calls@read.pkl is
    # committed and contains "read-value". Passing a different argument proves the
    # stored value is returned rather than the argument.
    actual = snapshot("different-value", key=key)

    assert actual == "read-value"


def test_returns_each_value_when_called_with_different_keys(pytester) -> None:
    """snapshot returns each stored value when called with different keys in one
    test."""
    pytester.makepyfile("""
        def test_inner(snapshot):
            actual_a = snapshot(77, key="a")
            actual_b = snapshot("(>'.')>", key="b")
            assert actual_a == 77
            assert actual_b == "(>'.')>"
    """)

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)


def test_user_defined_ditto_backend_raises_migration_error(pytester) -> None:
    """A user-defined ditto_backend fixture now fails with a migration error."""
    pytester.makepyfile("""
        import pytest

        @pytest.fixture
        def ditto_backend():
            return {}

        def test_inner(snapshot):
            snapshot("value", key="k")
    """)

    result = pytester.runpytest()

    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines([
        "*ditto_backend is superseded by target=, backend registration, and ditto_storage_options*"
    ])


def test_prune_does_not_delete_snapshots_from_sibling_tests(pytester) -> None:
    """--ditto-prune must not delete snapshots written by other tests in the same directory.

    Regression: the fallback fixture created a fresh FsspecMapping per test, giving
    each test its own _BackendRecord. Pass 1 of pytest_sessionfinish enumerated the
    entire shared .ditto/ directory for each record and subtracted only that one
    test's accessed keys, marking every sibling's snapshot as "not accessed" and
    deleting it. The fix caches the FsspecMapping by resolved root path so all
    tests in the same directory share one backend instance and one record.
    """
    pytester.makepyfile(
        test_alpha="""
            def test_alpha(snapshot):
                assert snapshot("alpha", key="value") == "alpha"
        """,
        test_beta="""
            def test_beta(snapshot):
                assert snapshot("beta", key="value") == "beta"
        """,
    )

    # First run: create both snapshots.
    pytester.runpytest().assert_outcomes(passed=2)

    # Second run with --ditto-prune: both tests still pass and nothing is pruned.
    result = pytester.runpytest("--ditto-prune")
    result.assert_outcomes(passed=2)
    result.stdout.no_fnmatch_line("*pruned*")


def test_shared_memory_target_does_not_report_false_unused(pytester) -> None:
    """Two tests sharing one memory target should not flag each other as unused."""
    pytester.makepyfile(
        test_alpha="""
            import ditto

            @ditto.record("json", target="memory://shared")
            def test_alpha(snapshot):
                assert snapshot({"value": "alpha"}, key="value") == {"value": "alpha"}
        """,
        test_beta="""
            import ditto

            @ditto.record("json", target="memory://shared")
            def test_beta(snapshot):
                assert snapshot({"value": "beta"}, key="value") == {"value": "beta"}
        """,
    )

    result = pytester.runpytest()

    result.assert_outcomes(passed=2)
    result.stderr.no_fnmatch_line("*│   unused*")


def test_module_field_uses_forward_slashes(pytester) -> None:
    """The module field in SnapshotKey always uses forward slashes, even on Windows.

    str() on a Path uses the OS path separator, producing backslashes on Windows.
    The fixture must use .as_posix() so that the storage key written to the
    backend and the key returned by __iter__ agree on all platforms.

    The test file is placed in a subdirectory so the module field contains a
    path separator, making the assertion meaningful.
    """
    pytester.makeconftest("""
        import pytest
        from ditto.backends import BACKEND_REGISTRY

        _backend = {}

        def _factory(uri: str, **kwargs):
            return _backend

        BACKEND_REGISTRY["test"] = _factory

        @pytest.fixture
        def stored_keys():
            return _backend
    """)
    subdir = pytester.mkdir("sub")
    subdir.joinpath("test_inner.py").write_text(
        "import ditto\n\n"
        "@ditto.record('pickle', target='test://shared')\n"
        "def test_inner(snapshot, stored_keys):\n"
        "    snapshot('v', key='k')\n"
        "    key = next(iter(stored_keys))\n"
        "    assert '\\\\' not in key, f'backslash in storage key: {key!r}'\n"
        "    assert '/' in key, f'expected forward slash in storage key: {key!r}'\n"
    )

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)


_ITER_RAISING_CONFTEST = """
    import pytest
    from collections.abc import MutableMapping, Iterator
    from ditto.backends import BACKEND_REGISTRY

    class {cls}(MutableMapping):
        def __init__(self): self._d = {{}}
        def __getitem__(self, k): return self._d[k]
        def __setitem__(self, k, v): self._d[k] = v
        def __delitem__(self, k): del self._d[k]
        def __len__(self): return len(self._d)
        def __iter__(self) -> Iterator:
            raise {exc}("{msg}")

    def _factory(uri: str, **kwargs):
        return {cls}()

    BACKEND_REGISTRY["testiter"] = _factory
"""


def test_session_completes_when_backend_iter_raises_not_implemented(pytester) -> None:
    """A backend that raises NotImplementedError from __iter__ emits a warning and
    does not crash pytest_sessionfinish."""
    pytester.makeconftest(
        _ITER_RAISING_CONFTEST.format(
            cls="NoIterBackend", exc="NotImplementedError", msg="no iteration"
        )
    )
    pytester.makepyfile(
        "import ditto\n\n"
        "@ditto.record('pickle', target='testiter://shared')\n"
        "def test_inner(snapshot):\n"
        "    snapshot('v', key='k')\n"
    )

    result = pytester.runpytest("-W", "always")

    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*does not support enumeration*"])


def test_session_completes_when_backend_iter_raises_ioerror(pytester) -> None:
    """A backend that raises a non-NotImplementedError (e.g. ConnectionError) from
    __iter__ emits a warning and does not crash pytest_sessionfinish.

    Regression: the original except clause only caught NotImplementedError.
    ConnectionError, PermissionError, and other I/O errors from remote backends
    (e.g. FsspecMapping's fs.find() call) propagated uncaught, preventing the
    session report from rendering.
    """
    pytester.makeconftest(
        _ITER_RAISING_CONFTEST.format(
            cls="BrokenIterBackend", exc="ConnectionError", msg="network gone"
        )
    )
    pytester.makepyfile(
        "import ditto\n\n"
        "@ditto.record('pickle', target='testiter://shared')\n"
        "def test_inner(snapshot):\n"
        "    snapshot('v', key='k')\n"
    )

    result = pytester.runpytest("-W", "always")

    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*raised ConnectionError*"])


def test_accepts_integer_as_key(pytester) -> None:
    """snapshot accepts an integer key and stores and returns the value correctly."""
    pytester.makepyfile("""
        def test_inner(snapshot):
            actual = snapshot(77, key=1029384756)
            assert actual == 77
    """)

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)
