from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import msgspec
import pytest
from click.testing import CliRunner

from ditto._lockfile import LockEntry
from ditto._manifest import BackendManifest, ManifestEntry
from ditto._result_inventory import inventory_result
from ditto._results import (
    RESULT_VERSION,
    Activity,
    Coverage,
    Identity,
    LockDelta,
    LockResult,
    Metadata,
    ObjectRef,
    OperationResult,
    TestResult as RunTests,
    decode_result,
    encode_result,
    safe_location,
)
from ditto.cli._pytest import cmd_update


def test_result_round_trip_preserves_units_identity_and_unknown_metadata():
    identity = Identity("tests/t.py::test_x[a::b]", "[bold]body:raw", "custom.json")
    result = OperationResult(
        RESULT_VERSION,
        "/project",
        RunTests(1, (identity.nodeid,), (identity.nodeid,)),
        (
            Activity(
                ObjectRef("local", "hashed.json", identity),
                "rewritten",
                "write",
                metadata=Metadata(19, None, "runtime"),
            ),
            Activity(
                ObjectRef("archive", "hashed.json", identity),
                "failed",
                "delete",
                "PermissionError",
            ),
        ),
        (Coverage("archive", "live", "failed", "Unavailable"),),
        lock=LockResult("written", (), (LockDelta("local", identity),)),
        completeness="incomplete",
    )
    assert decode_result(encode_result(result)) == result
    assert result.activity[1].metadata.modified is None
    assert len(result.lock.removed) == 1  # Entries, separate from object events.


@pytest.mark.parametrize(
    "data",
    [
        b'{"version":999,"scope":"x","tests":{"exit_code":0}}',
        b'{"version":1,"scope":"x","tests":{"exit_code":"ok"}}',
        b'{"version":1,"scope":"x"}',
        b"[]",
        b"{",
    ],
)
def test_invalid_handoff_is_rejected(data):
    with pytest.raises((ValueError, msgspec.ValidationError)):
        decode_result(data)


def test_inventory_keeps_failed_empty_and_unchecked_distinct():
    owner = LockEntry("test_x.py::test_t[12:00]", "raw:value", "json")
    result = inventory_result(
        [
            BackendManifest("empty", []),
            BackendManifest("failed", [], "password=supersecret"),
            BackendManifest("remote", [ManifestEntry("hashed", None, None)]),
            BackendManifest("disk", [ManifestEntry("unknown-hash", 12, 123.5)]),
        ],
        "tests/",
        {"empty": "live", "failed": "live", "remote": "lock", "disk": "disk"},
        {("remote", "hashed"): owner},
    )
    assert [(c.target, c.status) for c in result.coverage] == [
        ("empty", "checked"),
        ("failed", "failed"),
        ("remote", "unchecked"),
        ("disk", "checked"),
    ]
    assert result.items[0].object.identity == Identity(
        owner.nodeid, owner.key, owner.recorder
    )
    assert result.items[0].presence == "unknown"
    assert result.items[1].object.identity is None
    assert result.items[1].metadata.modified == 123.5
    assert "supersecret" not in repr(result)


def test_locations_do_not_persist_uri_authentication_or_signed_query_values():
    assert "secret" not in safe_location("s3://user:secret@bucket/path?token=secret")
    assert safe_location("simplecache::s3://user:secret@bucket/path?sig=secret") == (
        "simplecache::s3://user:***@bucket/path?sig=***"
    )


def _handoff(pytester, *args):
    path = pytester.path / "result.json"
    run = pytester.runpytest_subprocess(f"--ditto-result={path}", *args)
    return run, decode_result(path.read_bytes())


def test_private_handoff_reports_completed_writes_without_a_duplicate_panel(pytester):
    pytester.makepyfile("""
        import pytest
        @pytest.mark.parametrize("p", ["a::b"])
        def test_snapshot(snapshot, p):
            assert snapshot(1, key="[bold]raw:key") == 1
    """)
    run, result = _handoff(pytester)
    run.assert_outcomes(passed=1)
    assert "ditto snapshot report" not in run.stderr.str()
    (event,) = result.activity
    assert event.outcome == "created"
    assert event.object.identity == Identity(
        "test_private_handoff_reports_completed_writes_without_a_duplicate_panel.py::"
        "test_snapshot[a::b]",
        "[bold]raw:key",
        "json",
    )
    assert event.object.target == ".ditto"
    assert result.lock.status == "written"
    assert result.lock.added[0].identity == event.object.identity
    assert result.tests.exit_code == 0


def test_direct_pytest_keeps_the_existing_snapshot_report(pytester):
    pytester.makepyfile("""
        def test_snapshot(snapshot):
            snapshot(1, key="x")
    """)
    run = pytester.runpytest_subprocess()
    run.assert_outcomes(passed=1)
    assert "ditto snapshot report" in run.stderr.str()
    assert "created" in run.stderr.str()


def test_collection_error_produces_incomplete_data_not_empty_success(pytester):
    pytester.makepyfile("this is invalid python !!!")
    run, result = _handoff(pytester)
    assert run.ret == 2
    assert result.tests.exit_code == 2
    assert result.completeness == "incomplete"
    assert result.lock.status == "unchanged"
    assert result.activity == ()


def test_partial_writes_preserve_completed_and_failed_items_and_safe_reasons(pytester):
    pytester.makeconftest("""
        from ditto.backends import FsspecMapping
        original = FsspecMapping.__setitem__
        def write(self, key, value):
            if "@bad~" in key:
                raise PermissionError("credential=do-not-persist-this")
            return original(self, key, value)
        FsspecMapping.__setitem__ = write
    """)
    pytester.makepyfile("""
        def test_writes(snapshot):
            snapshot(1, key="good")
            snapshot(2, key="bad")
    """)
    run, result = _handoff(pytester, "--ditto-update")
    run.assert_outcomes(failed=1)
    assert [e.outcome for e in result.activity] == ["created", "failed"]
    assert result.activity[1].phase == "write"
    assert "PermissionError" in result.activity[1].reason
    assert "do-not-persist-this" not in (pytester.path / "result.json").read_text()
    assert len(list((pytester.path / ".ditto").glob("*"))) == 1
    assert (
        result.lock.status == "written"
    )  # Partial update appends confirmed creations.
    assert len(result.lock.added) == 1


def test_lock_failure_is_reported_separately_from_completed_snapshot_writes(pytester):
    pytester.makeconftest("""
        import ditto.plugin._lock as lock
        def fail(*args):
            raise PermissionError("password=never-in-artifact")
        lock.write_lockfile = fail
    """)
    pytester.makepyfile("""
        def test_snapshot(snapshot):
            snapshot(1, key="x")
    """)
    run, result = _handoff(pytester, "--ditto-update")
    assert run.ret == 1
    assert result.activity[0].outcome == "created"
    assert result.lock.status == "failed"
    assert result.lock.added == ()
    assert "never-in-artifact" not in (pytester.path / "result.json").read_text()
    assert not (pytester.path / "ditto.lock").exists()


def test_interruption_after_a_write_keeps_the_completed_event(pytester):
    pytester.makepyfile("""
        def test_snapshot(snapshot):
            snapshot(1, key="x")
            raise KeyboardInterrupt()
    """)
    run, result = _handoff(pytester)
    assert run.ret == 2  # pytest's interruption status, preserved by wrappers.
    assert result.completeness == "incomplete"
    assert result.activity[0].outcome == "created"
    assert result.tests.exit_code == 2


@pytest.mark.parametrize("payload,status", [(None, 0), (b"not json", 1), (b"{}", 2)])
def test_wrapper_unknown_handoff_preserves_child_exit_and_removes_artifacts(
    payload, status
):
    paths = []

    def child(command, **kwargs):
        assert command[:3] == [sys.executable, "-m", "pytest"]
        assert kwargs == {"check": False}  # pytest keeps inherited streams.
        path = Path(
            next(a.split("=", 1)[1] for a in command if a.startswith("--ditto-result="))
        )
        paths.append(path)
        if payload is not None:
            path.write_bytes(payload)
        return type("Child", (), {"returncode": status})()

    with patch("ditto.cli._operation.subprocess.run", side_effect=child):
        result = CliRunner().invoke(cmd_update, ["tests/", "-q"])
    assert result.exit_code == status
    assert "outcomes unknown" in result.stderr
    assert "No snapshot mutations" not in result.stdout
    assert not paths[0].parent.exists()


def test_wrapper_handles_launch_failure_without_raw_exception_secrets():
    with patch("ditto.cli._operation.subprocess.run", side_effect=OSError("secret")):
        result = CliRunner().invoke(cmd_update)
    assert result.exit_code == 1
    assert "Could not launch pytest" in result.stderr
    assert "secret" not in result.output


def test_cli_subprocess_preserves_test_output_and_prints_one_standalone_report(
    pytester,
):
    pytester.makepyfile("""
        def test_snapshot(snapshot):
            snapshot(1, key="[bold]x")
    """)
    run = pytester.run(
        sys.executable,
        "-c",
        "from ditto.cli import cli; cli()",
        "update",
        "-q",
    )
    assert run.ret == 0
    assert "1 passed" in run.stdout.str()
    assert run.stdout.str().count("Ditto report") == 1
    assert "1 created" in run.stdout.str()
    assert "[bold]x" in run.stdout.str()
    assert "ditto snapshot report" not in run.stderr.str()


def test_deselection_and_full_scope_remain_separate(pytester):
    pytester.makepyfile("""
        def test_one(snapshot):
            snapshot(1, key="a")
        def test_two(snapshot):
            snapshot(2, key="b")
    """)
    run, result = _handoff(pytester, "-k", "one")
    run.assert_outcomes(passed=1, deselected=1)
    assert result.scope_kind == "selected"
    assert len(result.tests.collected) == 2
    assert len(result.tests.deselected) == 1
    assert len(result.tests.passed) == 1


def test_xdist_remains_explicitly_unsupported_in_result_aggregation(pytester):
    pytester.makepyfile("""
        def test_snapshot(snapshot):
            snapshot(1, key="x")
    """)
    run, result = _handoff(pytester, "-n", "1")
    run.assert_outcomes(passed=1)
    assert result.completeness == "unsupported"
    assert "pytest-xdist" in result.reason


def test_handoff_write_failure_does_not_mask_pytest_status(pytester):
    pytester.makepyfile("""
        def test_snapshot(snapshot):
            snapshot(1, key="x")
            assert False
    """)
    run = pytester.runpytest_subprocess(
        f"--ditto-result={pytester.path / 'missing-dir' / 'result.json'}",
    )
    run.assert_outcomes(failed=1)
    assert "standalone result unavailable" in run.stderr.str()
    assert not (pytester.path / "missing-dir").exists()


def test_public_uri_parameters_keep_target_identity_distinct():
    a = "redis://host/0?namespace=a"
    b = "redis://host/0?namespace=b"
    assert safe_location(a) == a
    assert safe_location(b) == b


def test_interrupted_deletion_handoff_keeps_preceding_successes(pytester):
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
    pytester.makepyfile("""
        def test_snapshot(snapshot):
            snapshot(1, key="x")
    """)
    pytester.runpytest_subprocess().assert_outcomes(passed=1)
    directory = pytester.path / ".ditto"
    for key in ["a", "b"]:
        module = "test_interrupted_deletion_handoff_keeps_preceding_successes"
        (directory / f"{module}.old@{key}.json").write_text("1")
    run, result = _handoff(pytester, "--ditto-prune")
    assert run.ret != 0
    assert result.tests.exit_code == 2
    assert result.completeness == "incomplete"
    assert [e.outcome for e in result.activity if e.phase == "delete"] == [
        "deleted",
        "failed",
    ]
    assert len(list(directory.iterdir())) == 2  # Current object and second orphan.


def test_wrapper_final_failure_overrides_stale_handoff_status():
    result_data = OperationResult(
        RESULT_VERSION,
        "/project",
        RunTests(0),
        (Activity(ObjectRef("local", "x.json"), "created", "write"),),
        completeness="complete",
        scope_kind="full",
    )

    def child(command, **kwargs):
        path = Path(
            next(a.split("=", 1)[1] for a in command if a.startswith("--ditto-result="))
        )
        path.write_bytes(encode_result(result_data))
        return type("Child", (), {"returncode": 1})()

    with patch("ditto.cli._operation.subprocess.run", side_effect=child):
        result = CliRunner().invoke(cmd_update)
    assert result.exit_code == 1
    assert "does not match" in result.stderr
    assert "pytest exit 1" in result.stdout
    assert "Scope unknown" in result.stdout
    assert "1 created" in result.stdout


def test_update_lock_delta_does_not_imply_stored_object_deletion(pytester):
    test = pytester.makepyfile("""
        def test_snapshot(snapshot):
            snapshot(1, key="old")
    """)
    pytester.runpytest_subprocess().assert_outcomes(passed=1)
    test.write_text("""
def test_snapshot(snapshot):
    snapshot(1, key="new")
""")
    run, result = _handoff(pytester, "--ditto-update")
    run.assert_outcomes(passed=1)
    assert [entry.identity.key for entry in result.lock.added] == ["new"]
    assert [entry.identity.key for entry in result.lock.removed] == ["old"]
    assert [event.outcome for event in result.activity] == ["created"]
    assert len(list((pytester.path / ".ditto").iterdir())) == 2


def test_standalone_verify_reports_exact_drift_without_duplicate_legacy_report(
    pytester,
):
    pytester.makepyfile("""
        def test_snapshot(snapshot):
            snapshot(1, key="[bold]missing:key")
    """)
    pytester.runpytest_subprocess().assert_outcomes(passed=1)
    (stored,) = (pytester.path / ".ditto").iterdir()
    stored.unlink()
    run = pytester.run(
        sys.executable, "-c", "from ditto.cli import cli; cli()", "verify", "-q"
    )
    assert run.ret == 1
    assert "[bold]missing:key" in run.stdout.str()
    assert "missing: failed" in run.stdout.str()
    assert run.stdout.str().count("Ditto report") == 1
    assert "lock drift detected" not in run.stdout.str()
    assert not stored.exists()
