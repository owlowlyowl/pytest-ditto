"""What a pytest run writes to the standalone handoff (`--ditto-handoff`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ditto._handoff import (
    HANDOFF_VERSION,
    Handoff,
    LockOutcome,
    Outcome,
    SnapshotRef,
    read_handoff,
    write_handoff,
)


def _run(pytester: pytest.Pytester, *args: str) -> tuple[pytest.RunResult, Handoff]:
    path = pytester.path / "handoff.json"
    run = pytester.runpytest_subprocess(f"--ditto-handoff={path}", *args)
    return run, read_handoff(path)


def _outcomes(handoff: Handoff) -> list[str]:
    return [outcome.outcome for outcome in handoff.outcomes]


def test_restores_handoff_when_written_and_read(tmp_path: Path) -> None:
    """A handoff reads back exactly as it was written."""
    ref = SnapshotRef("file:///s", "t.test_x@k.json", "t.py::test_x[a::b]", "k", "json")
    handoff = Handoff(
        HANDOFF_VERSION,
        (Outcome(ref, "rewritten"), Outcome(SnapshotRef("s3://b", "old"), "deleted")),
        LockOutcome("written", added=1, removed=2),
    )
    path = tmp_path / "handoff.json"

    write_handoff(path, handoff)
    actual = read_handoff(path)

    expected = handoff
    assert actual == expected


@pytest.mark.parametrize(
    "data",
    [
        b'{"version":999}',
        b'{"version":1,"outcomes":[{"snapshot":{"target":"t"},"outcome":"x"}]}',
        b'{"version":1,"extra":1}',
        b"{",
    ],
)
def test_rejects_handoff_when_it_is_malformed(tmp_path: Path, data: bytes) -> None:
    """A handoff of another version or shape can't be read as an outcome."""
    path = tmp_path / "handoff.json"
    path.write_bytes(data)

    with pytest.raises(ValueError):
        read_handoff(path)


def test_records_exact_identity_when_key_contains_markup(
    pytester: pytest.Pytester,
) -> None:
    """Identity survives parameter delimiters and Rich markup characters."""
    pytester.makepyfile(
        test_orders="""
        import pytest
        @pytest.mark.parametrize("p", ["a::b"])
        def test_snapshot(snapshot, p):
            snapshot(1, key="[bold]raw:key")
    """
    )

    _, handoff = _run(pytester)
    snapshot = handoff.outcomes[0].snapshot
    actual = (snapshot.nodeid, snapshot.key, snapshot.recorder)

    expected = ("test_orders.py::test_snapshot[a::b]", "[bold]raw:key", "json")
    assert actual == expected


def test_records_rewrite_when_update_overwrites_snapshot(
    pytester: pytest.Pytester,
) -> None:
    """Overwriting an existing snapshot is a rewrite, not a creation."""
    pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(1, key="x")
    """
    )
    pytester.runpytest_subprocess().assert_outcomes(passed=1)

    _, handoff = _run(pytester, "--ditto-update")
    actual = _outcomes(handoff)

    expected = ["rewritten"]
    assert actual == expected


def test_keeps_completed_write_when_later_write_fails(
    pytester: pytest.Pytester,
) -> None:
    """A failed write doesn't hide the write that succeeded before it."""
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

    run, handoff = _run(pytester)

    run.assert_outcomes(failed=1)
    actual = _outcomes(handoff)
    expected = ["created", "write_failed"]
    assert actual == expected


def test_omits_error_message_when_write_fails(pytester: pytest.Pytester) -> None:
    """A backend's error message, which can carry secrets, stays out of the file."""
    pytester.makeconftest("""
        from ditto.backends import FsspecMapping
        def write(self, key, value):
            raise PermissionError("credential=do-not-persist-this")
        FsspecMapping.__setitem__ = write
    """)
    pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(1, key="x")
    """
    )

    _run(pytester)

    assert "do-not-persist-this" not in (pytester.path / "handoff.json").read_text()


def test_records_no_write_when_snapshot_cannot_serialize(
    pytester: pytest.Pytester,
) -> None:
    """A recorder error never reached storage, so it isn't a failed write."""
    pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(object(), key="x")
    """
    )

    run, handoff = _run(pytester)

    run.assert_outcomes(failed=1)
    actual = handoff.outcomes
    expected = ()
    assert actual == expected


def test_counts_lock_entries_when_update_replaces_a_key(
    pytester: pytest.Pytester,
) -> None:
    """The lock outcome counts the entries actually added and removed."""
    test = pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(1, key="old")
    """
    )
    pytester.runpytest_subprocess().assert_outcomes(passed=1)
    test.write_text("def test_snapshot(snapshot):\n    snapshot(1, key='new')\n")

    _, handoff = _run(pytester, "--ditto-update")
    actual = handoff.lock

    expected = LockOutcome("written", added=1, removed=1)
    assert actual == expected


def test_reports_unchanged_lock_when_nothing_new_is_recorded(
    pytester: pytest.Pytester,
) -> None:
    """A run that adds nothing to the lock reports it unchanged."""
    pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(1, key="x")
    """
    )
    pytester.runpytest_subprocess().assert_outcomes(passed=1)

    _, handoff = _run(pytester)
    actual = handoff.lock

    expected = LockOutcome("unchanged")
    assert actual == expected


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
    pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(1, key="x")
    """
    )

    _, handoff = _run(pytester, "--ditto-update")
    actual = (_outcomes(handoff), handoff.lock.status)

    expected = (["created"], "failed")
    assert actual == expected


def test_reports_refused_lock_when_rebuild_is_narrowed(
    pytester: pytest.Pytester,
) -> None:
    """A narrowed --ditto-lock is refused rather than failed."""
    pytester.makepyfile(
        test_orders="""
        def test_one(snapshot):
            snapshot(1, key="a")
        def test_two(snapshot):
            snapshot(2, key="b")
    """
    )

    _, handoff = _run(pytester, "--ditto-lock", "-k", "one")
    actual = handoff.lock.status

    expected = "refused"
    assert actual == expected


@pytest.mark.parametrize(
    "flag,outcome",
    [("--ditto-prune", "deleted"), ("--ditto-prune-dry-run", "would_delete")],
)
def test_records_orphan_when_pruning(
    pytester: pytest.Pytester, flag: str, outcome: str
) -> None:
    """A prune records each orphan it deleted, or would delete, by storage key."""
    pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(1, key="x")
    """
    )
    pytester.runpytest_subprocess().assert_outcomes(passed=1)
    (pytester.path / ".ditto" / "test_orders.old@a.json").write_text("1")

    _, handoff = _run(pytester, flag)
    actual = [(o.snapshot.storage_key, o.outcome) for o in handoff.outcomes]

    expected = [("test_orders.old@a.json", outcome)]
    assert actual == expected


def test_records_failed_deletion_when_orphan_cannot_be_deleted(
    pytester: pytest.Pytester,
) -> None:
    """A deletion that raised is recorded as failed, not deleted."""
    pytester.makeconftest("""
        from ditto.backends import FsspecMapping
        def delete(self, key):
            raise PermissionError("read-only")
        FsspecMapping.__delitem__ = delete
    """)
    pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(1, key="x")
    """
    )
    pytester.runpytest_subprocess().assert_outcomes(passed=1)
    (pytester.path / ".ditto" / "test_orders.old@a.json").write_text("1")

    _, handoff = _run(pytester, "--ditto-prune")
    actual = _outcomes(handoff)

    expected = ["delete_failed"]
    assert actual == expected


def test_writes_handoff_when_collection_fails(pytester: pytest.Pytester) -> None:
    """A collection error still produces a handoff, with nothing written."""
    pytester.makepyfile("this is invalid python !!!")

    run, handoff = _run(pytester)
    actual = (run.ret, handoff.outcomes)

    expected = (pytest.ExitCode.INTERRUPTED, ())
    assert actual == expected


def test_omits_session_report_when_writing_handoff(pytester: pytest.Pytester) -> None:
    """The standalone CLI prints the report, so pytest doesn't print its own."""
    pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(1, key="x")
    """
    )

    run, _ = _run(pytester)

    assert "ditto snapshot report" not in run.stderr.str()


def test_prints_session_report_when_pytest_runs_directly(
    pytester: pytest.Pytester,
) -> None:
    """Ordinary pytest keeps its own snapshot report."""
    pytester.makepyfile(
        test_orders="""
        def test_snapshot(snapshot):
            snapshot(1, key="x")
    """
    )

    run = pytester.runpytest_subprocess()

    assert "ditto snapshot report" in run.stderr.str()
