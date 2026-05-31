import json

pytest_plugins = ["pytester"]

PRUNE_MODULE = '''
def test_alpha(snapshot):
    assert snapshot(1, key="a") == 1

def test_beta(snapshot):
    assert snapshot(2, key="b") == 2
'''


def _seed_lock(pytester):
    pytester.makepyfile(test_mod=PRUNE_MODULE)
    pytester.runpytest_subprocess()
    return pytester.path / "ditto.lock"


def _backend_files(pytester):
    return {p.name for p in (pytester.path / ".ditto").iterdir()}


def _drop_beta_from_lock(lock_path):
    data = json.loads(lock_path.read_text())
    target = next(iter(data["targets"].values()))
    target["entries"] = [e for e in target["entries"] if "test_beta" not in e["nodeid"]]
    lock_path.write_text(json.dumps(data))


def test_prune_deletes_a_genuine_orphan(pytester):
    """A backend snapshot with no lock entry (not created this run) is deleted."""
    lock_path = _seed_lock(pytester)
    _drop_beta_from_lock(lock_path)

    result = pytester.runpytest_subprocess("--ditto-prune")

    assert result.ret == 0
    files = _backend_files(pytester)
    assert not any("test_beta" in f for f in files)
    assert any("test_alpha" in f for f in files)


def test_prune_does_not_delete_a_newly_created_snapshot(pytester):
    """A snapshot created this run but not yet in the lock (unsynced) is kept."""
    _seed_lock(pytester)
    pytester.makepyfile(
        test_mod=PRUNE_MODULE
        + '''
def test_gamma(snapshot):
    assert snapshot(3, key="c") == 3
'''
    )

    result = pytester.runpytest_subprocess("--ditto-prune")

    assert result.ret == 0
    assert any("test_gamma" in f for f in _backend_files(pytester))


def test_prune_refuses_when_no_lockfile_exists(pytester):
    """Prune requires a committed lock; with none it refuses (non-zero)."""
    pytester.makepyfile(test_mod=PRUNE_MODULE)

    result = pytester.runpytest_subprocess("--ditto-prune")

    assert result.ret != 0
    result.stdout.fnmatch_lines(["*no ditto.lock*"])


def test_prune_dry_run_reports_orphan_without_deleting(pytester):
    """--ditto-prune-dry-run lists the orphan but leaves the backend untouched."""
    lock_path = _seed_lock(pytester)
    _drop_beta_from_lock(lock_path)

    result = pytester.runpytest_subprocess("--ditto-prune-dry-run")

    assert result.ret == 0
    assert any("test_beta" in f for f in _backend_files(pytester))  # NOT deleted
    result.stderr.fnmatch_lines(["*would prune*"])
