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


def test_broken_ditto_backend_dependency_fails_loudly(pytester) -> None:
    """A ditto_backend fixture whose own dependency is missing fails the test.

    Regression: previously the FixtureLookupError was caught unconditionally,
    silently falling back to LocalMapping and hiding the broken backend.
    """
    pytester.makepyfile("""
        import pytest

        @pytest.fixture
        def ditto_backend(nonexistent_dep):
            return nonexistent_dep

        def test_inner(snapshot):
            snapshot("value", key="k")
    """)

    result = pytester.runpytest()

    result.assert_outcomes(errors=1)


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


def test_accepts_integer_as_key(pytester) -> None:
    """snapshot accepts an integer key and stores and returns the value correctly."""
    pytester.makepyfile("""
        def test_inner(snapshot):
            actual = snapshot(77, key=1029384756)
            assert actual == 77
    """)

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)
