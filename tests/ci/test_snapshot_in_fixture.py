def test_module_scoped_fixture_cannot_use_snapshot_fixture(pytester) -> None:
    """A module-scoped fixture cannot request the function-scoped snapshot fixture."""
    pytester.makepyfile("""
        import pytest
        import ditto

        @pytest.fixture(scope="module")
        def _module_scoped_data(snapshot):
            return snapshot(1, key="data")

        @ditto.yaml
        def test_inner(snapshot, _module_scoped_data):
            result = _module_scoped_data + 34
            assert result == snapshot(result, key="result")
    """)

    result = pytester.runpytest()

    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*ScopeMismatch*"])
