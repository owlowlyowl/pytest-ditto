"""What the end-of-session snapshot report says a run did to snapshots and the lock."""

from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

from ditto._lockfile import LockOutcome
from ditto._report import render_session_report
from ditto.snapshot import SnapshotKey, SnapshotWrite


ONE_SNAPSHOT = """
def test_snapshot(snapshot):
    snapshot(1, key="x")
"""


def _failing_writes(pattern: str) -> str:
    """A conftest whose backend raises on writes to keys containing `pattern`."""
    return f"""
        from ditto.backends import FsspecMapping
        original = FsspecMapping.__setitem__
        def write(self, key, value):
            if {pattern!r} in key:
                raise PermissionError("read-only")
            return original(self, key, value)
        FsspecMapping.__setitem__ = write
    """


def test_lists_rewrite_as_rewritten_when_update_overwrites_snapshot(
    pytester: pytest.Pytester,
) -> None:
    """Overwriting an existing snapshot is reported as rewritten, not created."""
    pytester.makepyfile(test_orders=ONE_SNAPSHOT)
    pytester.runpytest_subprocess().assert_outcomes(passed=1)

    run = pytester.runpytest_subprocess("--ditto-update")

    run.stderr.fnmatch_lines(["*1 rewritten*", "*rewritten*x*json*"])
    assert "created" not in run.stderr.str()


def test_lists_snapshot_as_not_written_when_backend_rejects_it(
    pytester: pytest.Pytester,
) -> None:
    """A write the backend raised on is reported, not silently dropped."""
    pytester.makeconftest(_failing_writes("@x~"))
    pytester.makepyfile(test_orders=ONE_SNAPSHOT)

    run = pytester.runpytest_subprocess()

    run.assert_outcomes(failed=1)
    run.stderr.fnmatch_lines(["*1 not written*", "*not written*x*json*"])


def test_keeps_completed_write_when_later_write_fails(
    pytester: pytest.Pytester,
) -> None:
    """A failed write doesn't hide the write that succeeded before it."""
    pytester.makeconftest(_failing_writes("@bad~"))
    pytester.makepyfile(
        test_orders="""
        def test_writes(snapshot):
            snapshot(1, key="good")
            snapshot(2, key="bad")
    """
    )

    run = pytester.runpytest_subprocess()

    run.stderr.fnmatch_lines(["*created*good*json*", "*not written*bad*json*"])


def test_lists_no_failed_write_when_snapshot_cannot_serialize(
    pytester: pytest.Pytester,
) -> None:
    """A recorder error never reached storage, so it isn't a failed write."""
    pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(object(), key="x")
    """
    )

    run = pytester.runpytest_subprocess()

    run.assert_outcomes(failed=1)
    assert "not written" not in run.stderr.str()


def test_counts_lock_entries_when_update_replaces_a_key(
    pytester: pytest.Pytester,
) -> None:
    """The lock row counts the entries actually added and removed."""
    test = pytester.makepyfile(test_orders=ONE_SNAPSHOT)
    pytester.runpytest_subprocess().assert_outcomes(passed=1)
    test.write_text("def test_snapshot(snapshot):\n    snapshot(1, key='new')\n")

    run = pytester.runpytest_subprocess("--ditto-update")

    run.stderr.fnmatch_lines(["*lock*ditto.lock written*1 added*1 removed*"])


def test_omits_entry_counts_when_rebuild_replaces_an_unreadable_lock(
    pytester: pytest.Pytester,
) -> None:
    """Replacing a lock that couldn't be read can't say how many entries changed."""
    test = pytester.makepyfile(
        test_orders="""
        def test_one(snapshot):
            snapshot(1, key="a")
        def test_two(snapshot):
            snapshot(2, key="b")
    """
    )
    pytester.runpytest_subprocess().assert_outcomes(passed=2)
    lock = pytester.path / "ditto.lock"
    lock.write_text(lock.read_text().replace('"version": 1', '"version": 999'))
    test.write_text("def test_one(snapshot):\n    snapshot(1, key='a')\n")

    run = pytester.runpytest_subprocess("--ditto-lock")

    run.stderr.fnmatch_lines(["*lock*ditto.lock written*previous entries unknown*"])
    assert "added" not in run.stderr.str()


def test_prints_no_report_when_run_changes_nothing(
    pytester: pytest.Pytester,
) -> None:
    """A run that writes no snapshot and leaves the lock unchanged stays silent."""
    pytester.makepyfile(test_orders=ONE_SNAPSHOT)
    pytester.runpytest_subprocess().assert_outcomes(passed=1)

    run = pytester.runpytest_subprocess()

    assert "ditto snapshot report" not in run.stderr.str()


def test_reports_failed_lock_when_lock_cannot_be_written(
    pytester: pytest.Pytester,
) -> None:
    """A lock write failure is reported apart from the snapshot write it follows."""
    pytester.makeconftest("""
        import ditto.plugin._lock as lock
        def fail(*args):
            raise PermissionError("read-only")
        lock.write_lockfile = fail
    """)
    pytester.makepyfile(test_orders=ONE_SNAPSHOT)

    run = pytester.runpytest_subprocess("--ditto-update")

    run.stderr.fnmatch_lines([
        "*1 created*",
        "*lock*ditto.lock failed*PermissionError*",
    ])


def test_reports_refused_lock_when_rebuild_is_narrowed(
    pytester: pytest.Pytester,
) -> None:
    """A narrowed --ditto-lock is reported as refused, saying it was narrowed."""
    pytester.makepyfile(
        test_orders="""
        def test_one(snapshot):
            snapshot(1, key="a")
        def test_two(snapshot):
            snapshot(2, key="b")
    """
    )

    run = pytester.runpytest_subprocess("--ditto-lock", "-k", "one")

    run.stderr.fnmatch_lines(["*lock*ditto.lock refused*narrowed run*"])


def test_reports_refused_lock_when_rebuild_has_failing_tests(
    pytester: pytest.Pytester,
) -> None:
    """A --ditto-lock run with a failing test is refused, saying tests failed."""
    pytester.makepyfile(
        test_orders="""
        def test_one(snapshot):
            snapshot(1, key="a")
        def test_two():
            assert False
    """
    )

    run = pytester.runpytest_subprocess("--ditto-lock")

    run.stderr.fnmatch_lines(["*lock*ditto.lock refused*tests failed*"])


def test_lists_no_failed_write_when_write_is_interrupted(
    pytester: pytest.Pytester,
) -> None:
    """An interrupt during a write isn't a failed write: it may have finished."""
    pytester.makeconftest("""
        from ditto.backends import FsspecMapping
        def write(self, key, value):
            raise KeyboardInterrupt
        FsspecMapping.__setitem__ = write
    """)
    pytester.makepyfile(test_orders=ONE_SNAPSHOT)

    run = pytester.runpytest_subprocess()

    assert run.ret == pytest.ExitCode.INTERRUPTED
    assert "not written" not in run.stderr.str()


def test_lists_snapshot_as_not_pruned_when_deletion_fails(
    pytester: pytest.Pytester,
) -> None:
    """A deletion that raised is reported as not pruned, not as pruned."""
    pytester.makeconftest("""
        from ditto.backends import FsspecMapping
        def delete(self, key):
            raise PermissionError("read-only")
        FsspecMapping.__delitem__ = delete
    """)
    pytester.makepyfile(test_orders=ONE_SNAPSHOT)
    pytester.runpytest_subprocess().assert_outcomes(passed=1)
    (pytester.path / ".ditto" / "test_orders.old@a.json").write_text("1")

    run = pytester.runpytest_subprocess("--ditto-prune")

    run.stderr.fnmatch_lines(["*not pruned*1*", "*test_orders.old@a.json*"])
    assert "  pruned" not in run.stderr.str()


def test_prints_report_when_only_the_lock_changed() -> None:
    """A lock rebuild that wrote no snapshot still says the lock was written."""
    stream = StringIO()

    render_session_report(
        lock=LockOutcome("written", added=0, removed=2),
        console=Console(file=stream, width=100),
    )

    assert "ditto.lock written  0 added, 2 removed" in stream.getvalue()


def _write(nodeid: str, key: str, outcome: str = "created") -> SnapshotWrite:
    file, _, test = nodeid.partition("::")
    module = file.removesuffix(".py")
    return SnapshotWrite(SnapshotKey(module, test, key, "json", nodeid), outcome)


def _report_body(writes: list[SnapshotWrite]) -> list[str]:
    """The report's non-blank lines, without the panel's borders."""
    stream = StringIO()
    render_session_report(
        writes=writes, console=Console(file=stream, width=100, color_system=None)
    )
    lines = [
        line[2:-2].rstrip()
        for line in stream.getvalue().splitlines()
        if line.startswith("│")
    ]
    return [line for line in lines if line.startswith(" ") or line[:1].isalnum()]


def test_groups_written_snapshots_under_their_file_and_test() -> None:
    """Each write is listed under its file and test, keys aligned within a test."""
    writes = [
        _write("tests/test_a.py::test_one", "x"),
        _write("tests/test_a.py::test_one", "longer", "write_failed"),
        _write("tests/test_b.py::test_two[p]", "y", "rewritten"),
    ]

    actual = _report_body(writes)[1:]

    expected = [
        "tests/test_a.py",
        "  test_one",
        "    created      x       json",
        "    not written  longer  json",
        "tests/test_b.py",
        "  test_two[p]",
        "    rewritten    y  json",
    ]
    assert actual == expected


def test_opens_with_a_count_of_each_write_outcome() -> None:
    """The first line counts created, rewritten and failed writes."""
    writes = [
        _write("tests/test_a.py::test_one", "a"),
        _write("tests/test_a.py::test_one", "b"),
        _write("tests/test_a.py::test_one", "c", "rewritten"),
        _write("tests/test_a.py::test_one", "d", "write_failed"),
    ]

    actual = _report_body(writes)[0]

    expected = "2 created · 1 rewritten · 1 not written"
    assert actual == expected


def test_shows_a_key_with_markup_literally() -> None:
    """A key that looks like Rich markup is printed as written."""
    writes = [_write("tests/test_a.py::test_one", "[red]x[/red]")]

    actual = _report_body(writes)

    assert "    created      [red]x[/red]  json" in actual


def test_groups_a_write_without_a_node_id_under_its_module_and_test() -> None:
    """A Snapshot built outside the fixture is grouped by the key's own names."""
    key = SnapshotKey("tests/test_a", "test_one", "x", "json")

    actual = _report_body([SnapshotWrite(key, "created")])[1:3]

    expected = ["tests/test_a", "  test_one"]
    assert actual == expected
