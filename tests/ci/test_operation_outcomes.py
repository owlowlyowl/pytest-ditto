from __future__ import annotations

import pytest

from ditto._results import (
    Identity,
    decode_result,
)


def _handoff(pytester: pytest.Pytester, *args: str):
    path = pytester.path / "result.json"
    run = pytester.runpytest_subprocess(f"--ditto-result={path}", *args)
    return run, decode_result(path.read_bytes())


def test_preserves_exact_identity_when_snapshot_key_contains_markup(
    pytester: pytest.Pytester,
) -> None:
    """Snapshot identity survives parameter delimiters and Rich markup characters."""
    pytester.makepyfile(
        test_orders="""
        import pytest
        @pytest.mark.parametrize("p", ["a::b"])
        def test_snapshot(snapshot, p):
            assert snapshot(1, key="[bold]raw:key") == 1
    """
    )

    _, result = _handoff(pytester)
    actual = result.activity[0].object.identity

    expected = Identity("test_orders.py::test_snapshot[a::b]", "[bold]raw:key", "json")
    assert actual == expected


def test_marks_coverage_incomplete_when_collection_fails(
    pytester: pytest.Pytester,
) -> None:
    """Collection failure cannot be reported as complete discovery."""
    pytester.makepyfile("this is invalid python !!!")

    run, result = _handoff(pytester)
    actual = (
        run.ret,
        result.tests.exit_code,
        result.completeness,
        result.lock.status,
        result.activity,
    )
    expected = (
        2,
        2,
        "incomplete",
        "unchanged",
        (),
    )

    assert actual == expected


def test_preserves_completed_writes_when_later_snapshot_write_fails(
    pytester: pytest.Pytester,
) -> None:
    """A failed write does not erase earlier confirmed mutations."""
    pytester.makeconftest("""
        from ditto.backends import FsspecMapping
        original = FsspecMapping.__setitem__
        def write(self, key, value):
            if "@bad~" in key:
                raise PermissionError("credential=do-not-persist-this")
            return original(self, key, value)
        FsspecMapping.__setitem__ = write
    """)
    pytester.makepyfile(
        test_orders="""
        def test_writes(snapshot):
            snapshot(1, key="good")
            snapshot(2, key="bad")
    """
    )

    run, result = _handoff(pytester, "--ditto-update")

    run.assert_outcomes(failed=1)
    actual = (
        (result.activity[0].outcome, result.activity[1].outcome),
        result.activity[1].phase,
        len(list((pytester.path / ".ditto").glob("*"))),
        result.lock.status,
        len(result.lock.added),
    )
    expected = (
        ("created", "failed"),
        "write",
        1,
        "written",
        1,
    )

    assert actual == expected
    assert "PermissionError" in result.activity[1].reason
    assert "do-not-persist-this" not in (pytester.path / "result.json").read_text()


def test_reports_lock_failure_when_snapshot_write_succeeds(
    pytester: pytest.Pytester,
) -> None:
    """Lock publication failure remains distinct from completed snapshot writes."""
    pytester.makeconftest("""
        import ditto.plugin._lock as lock
        def fail(*args):
            raise PermissionError("password=never-in-artifact")
        lock.write_lockfile = fail
    """)
    pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(1, key="x")
    """
    )

    run, result = _handoff(pytester, "--ditto-update")
    actual = (
        run.ret,
        result.activity[0].outcome,
        result.lock.status,
        result.lock.added,
    )
    expected = (
        1,
        "created",
        "failed",
        (),
    )

    assert actual == expected
    assert "never-in-artifact" not in (pytester.path / "result.json").read_text()
    assert not (pytester.path / "ditto.lock").exists()


def test_preserves_completed_write_when_pytest_is_interrupted(
    pytester: pytest.Pytester,
) -> None:
    """Interruption retains the completed write and a failing exit status."""
    pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(1, key="x")
            raise KeyboardInterrupt()
    """
    )

    run, result = _handoff(pytester)
    actual = (
        run.ret,
        result.completeness,
        result.activity[0].outcome,
        result.tests.exit_code,
    )
    expected = (
        2,
        "incomplete",
        "created",
        2,
    )

    assert actual == expected


def test_marks_scope_selected_when_tests_are_deselected(
    pytester: pytest.Pytester,
) -> None:
    """Deselection prevents claiming full-suite coverage."""
    pytester.makepyfile(
        test_orders="""
        def test_one(snapshot):
            snapshot(1, key="a")
        def test_two(snapshot):
            snapshot(2, key="b")
    """
    )

    run, result = _handoff(pytester, "-k", "one")

    run.assert_outcomes(passed=1, deselected=1)
    actual = (
        result.scope_kind,
        len(result.tests.collected),
        len(result.tests.deselected),
        len(result.tests.passed),
    )
    expected = (
        "selected",
        2,
        1,
        1,
    )

    assert actual == expected


def test_marks_aggregation_unsupported_when_xdist_runs(
    pytester: pytest.Pytester,
) -> None:
    """Distributed pytest explicitly reports unsupported result aggregation."""
    pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(1, key="x")
    """
    )

    run, result = _handoff(pytester, "-n", "1")

    run.assert_outcomes(passed=1)
    actual = result.completeness
    expected = "unsupported"

    assert actual == expected
    assert "pytest-xdist" in result.reason


def test_preserves_confirmed_deletion_when_pruning_is_interrupted(
    pytester: pytest.Pytester,
) -> None:
    """Interrupted pruning retains the preceding confirmed deletion."""
    pytester.makeconftest("""
        from ditto.backends import FsspecMapping
        original = FsspecMapping.__delitem__
        deleted = 0
        def delete(self, key):
            global deleted
            if deleted == 1:
                raise KeyboardInterrupt()
            original(self, key)
            deleted += 1
        FsspecMapping.__delitem__ = delete
    """)
    pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(1, key="x")
    """
    )
    pytester.runpytest_subprocess().assert_outcomes(passed=1)
    directory = pytester.path / ".ditto"
    (directory / "test_orders.old@a.json").write_text("1")
    (directory / "test_orders.old@b.json").write_text("1")

    run, result = _handoff(pytester, "--ditto-prune")
    actual = (
        result.tests.exit_code,
        result.completeness,
        (result.activity[-2].outcome, result.activity[-1].outcome),
        len(list(directory.iterdir())),
    )
    expected = (
        2,
        "incomplete",
        ("deleted", "failed"),
        2,
    )

    assert actual == expected
    assert run.ret != 0


def test_keeps_stored_objects_when_update_removes_old_lock_entry(
    pytester: pytest.Pytester,
) -> None:
    """Lock entry removal does not claim physical object deletion."""
    test = pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(1, key="old")
    """
    )
    pytester.runpytest_subprocess().assert_outcomes(passed=1)
    test.write_text("""
def test_snapshot(snapshot):
    snapshot(1, key="new")
""")

    run, result = _handoff(pytester, "--ditto-update")

    run.assert_outcomes(passed=1)
    actual = (
        result.lock.added[0].identity.key,
        result.lock.removed[0].identity.key,
        result.activity[0].outcome,
        len(list((pytester.path / ".ditto").iterdir())),
    )
    expected = (
        "new",
        "old",
        "created",
        2,
    )

    assert actual == expected
