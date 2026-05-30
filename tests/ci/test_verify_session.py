import json
import types

from ditto.exceptions import DittoWarning
from ditto.plugin import _warn_if_lockfile_ignored
from ditto.snapshot import _SessionTracker

pytest_plugins = ["pytester"]


def test_ditto_warning_is_a_user_warning():
    """DittoWarning subclasses UserWarning so existing filters still apply."""
    assert issubclass(DittoWarning, UserWarning)


def test_gitignore_guard_warns_with_ditto_category(tmp_path, recwarn):
    """The .gitignore guard emits its advisory under the DittoWarning category."""
    (tmp_path / ".gitignore").write_text("ditto.lock\n")

    _warn_if_lockfile_ignored(types.SimpleNamespace(rootpath=tmp_path))

    assert any(issubclass(w.category, DittoWarning) for w in recwarn.list)


def test_tracker_registers_target_backend():
    """A target id maps to its (scheme, backend) for later enumeration."""
    tracker = _SessionTracker()
    backend = object()

    tracker.register_target_backend("tests/.ditto", "file", backend)

    assert tracker.target_backends["tests/.ditto"] == ("file", backend)


def test_tracker_reset_clears_target_backends():
    """Reset drops registered target backends."""
    tracker = _SessionTracker()
    tracker.register_target_backend("tests/.ditto", "file", object())

    tracker.reset()

    assert tracker.target_backends == {}


VERIFY_MODULE = '''
def test_alpha(snapshot):
    assert snapshot(1, key="a") == 1

def test_beta(snapshot):
    assert snapshot(2, key="b") == 2
'''


def _seed_lock(pytester):
    """Run once to create snapshots + ditto.lock, returning the lock path."""
    pytester.makepyfile(test_mod=VERIFY_MODULE)
    pytester.runpytest_subprocess()
    return pytester.path / "ditto.lock"


def test_verify_passes_when_backend_matches_lock(pytester):
    """A clean committed lock + matching snapshots verifies green."""
    _seed_lock(pytester)

    result = pytester.runpytest_subprocess("--ditto-verify")

    assert result.ret == 0


def test_verify_fails_when_a_snapshot_is_missing(pytester):
    """A lock entry whose snapshot file is gone fails verify."""
    _seed_lock(pytester)
    snap_dir = pytester.path / ".ditto"
    next(p for p in snap_dir.iterdir() if "test_alpha" in p.name).unlink()

    result = pytester.runpytest_subprocess("--ditto-verify")

    assert result.ret != 0


def test_verify_fails_on_orphan_backend_snapshot(pytester):
    """A backend snapshot with no lock entry fails verify."""
    lock_path = _seed_lock(pytester)
    data = json.loads(lock_path.read_text())
    target = next(iter(data["targets"].values()))
    target["entries"] = [e for e in target["entries"] if "test_beta" not in e["nodeid"]]
    lock_path.write_text(json.dumps(data))  # beta now an orphan on the backend

    result = pytester.runpytest_subprocess("--ditto-verify")

    assert result.ret != 0


def test_verify_fails_when_a_test_produces_an_unrecorded_snapshot(pytester):
    """A new key not in the committed lock (unsynced) fails verify."""
    _seed_lock(pytester)
    pytester.makepyfile(
        test_mod=VERIFY_MODULE
        + '''
def test_gamma(snapshot):
    assert snapshot(3, key="c") == 3
'''
    )

    result = pytester.runpytest_subprocess("--ditto-verify")

    assert result.ret != 0


def test_verify_is_read_only_and_does_not_recreate_a_deleted_snapshot(pytester):
    """Read-only verify must not rewrite the deleted snapshot or the lock."""
    lock_path = _seed_lock(pytester)
    lock_before = lock_path.read_bytes()
    snap_dir = pytester.path / ".ditto"
    deleted = next(p for p in snap_dir.iterdir() if "test_alpha" in p.name)
    deleted.unlink()

    pytester.runpytest_subprocess("--ditto-verify")

    assert not deleted.exists()  # verify did not recreate the snapshot
    assert lock_path.read_bytes() == lock_before  # lock left untouched


def test_verify_cannot_combine_with_update(pytester):
    """--ditto-verify (read-only) is rejected alongside a write flag."""
    pytester.makepyfile(test_mod=VERIFY_MODULE)

    result = pytester.runpytest_subprocess("--ditto-verify", "--ditto-update")

    assert result.ret != 0
    result.stderr.fnmatch_lines(["*read-only*"])


def test_verify_fails_when_no_lockfile_exists(pytester):
    """Verifying with no ditto.lock is an error, not a silent pass."""
    pytester.makepyfile(test_mod=VERIFY_MODULE)
    # no prior run, so no ditto.lock

    result = pytester.runpytest_subprocess("--ditto-verify")

    assert result.ret != 0
    result.stdout.fnmatch_lines(["*no ditto.lock*"])


def test_verify_partial_run_warns_but_passes_when_clean(pytester):
    """A clean partial verify passes but warns it was partial."""
    _seed_lock(pytester)

    result = pytester.runpytest_subprocess("--ditto-verify", "-k", "test_alpha")

    assert result.ret == 0
    # Match the warning text specifically (not the temp-dir name in the header).
    result.stdout.fnmatch_lines(["*partial verification*"])
