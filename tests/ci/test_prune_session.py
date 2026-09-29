import json

pytest_plugins = ["pytester"]

PRUNE_MODULE = """
def test_alpha(snapshot):
    assert snapshot(1, key="a") == 1

def test_beta(snapshot):
    assert snapshot(2, key="b") == 2
"""


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
        + """
def test_gamma(snapshot):
    assert snapshot(3, key="c") == 3
"""
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


def test_prune_and_dry_run_are_mutually_exclusive(pytester):
    """--ditto-prune and --ditto-prune-dry-run cannot be combined."""
    pytester.makepyfile(test_mod=PRUNE_MODULE)

    result = pytester.runpytest_subprocess("--ditto-prune", "--ditto-prune-dry-run")

    assert result.ret != 0
    result.stderr.fnmatch_lines(["*--ditto-prune*--ditto-prune-dry-run*"])


# ── A shared target isn't pruned without --ditto-prune-shared (#161) ─────────

API_MODULE = "def test_old(snapshot):\n    snapshot(1, key='a')\n"
API_MODULE_WITH_NEW_TEST = (
    API_MODULE + "\ndef test_new(snapshot):\n    snapshot(2, key='b')\n"
)


def _checkout(pytester, name, shared, module):
    """Make a checkout with its own rootdir, whose tests use the `shared` target."""
    root = pytester.mkdir(name)
    (root / "pytest.ini").write_text(f"[pytest]\nditto_target = file://{shared}\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_api.py").write_text(module)
    return root


def _run_in(pytester, monkeypatch, root, *args):
    monkeypatch.chdir(root)
    return pytester.runpytest_subprocess(*args)


def _branches_sharing_a_target(pytester, monkeypatch):
    """Two branches of one project share a target; only branch `b` has
    `test_new`, whose snapshot looks like an orphan to branch `a`."""
    shared = pytester.mkdir("shared")
    a = _checkout(pytester, "a", shared, API_MODULE)
    b = _checkout(pytester, "b", shared, API_MODULE_WITH_NEW_TEST)
    _run_in(pytester, monkeypatch, b, "--ditto-lock").assert_outcomes(passed=2)
    _run_in(pytester, monkeypatch, a, "--ditto-lock").assert_outcomes(passed=1)
    return a, shared


def test_prune_does_not_delete_from_a_shared_target(pytester, monkeypatch):
    """Prune leaves another branch's snapshot on a shared target alone, says
    why, and fails the run."""
    a, shared = _branches_sharing_a_target(pytester, monkeypatch)

    result = _run_in(pytester, monkeypatch, a, "--ditto-prune")

    assert result.ret != 0
    result.stdout.fnmatch_lines([
        "*ditto prune: not deleting 1 snapshot(s) from*--ditto-prune-shared*"
    ])
    assert any("test_new" in p.name for p in shared.iterdir())


def test_prune_deletes_from_a_shared_target_with_prune_shared(pytester, monkeypatch):
    """--ditto-prune-shared is the user saying the target is theirs alone."""
    a, shared = _branches_sharing_a_target(pytester, monkeypatch)

    result = _run_in(pytester, monkeypatch, a, "--ditto-prune", "--ditto-prune-shared")

    assert result.ret == 0
    assert not any("test_new" in p.name for p in shared.iterdir())
    assert any("test_old" in p.name for p in shared.iterdir())


def test_prune_dry_run_lists_a_shared_target_s_orphans(pytester, monkeypatch):
    """A dry run deletes nothing, so it lists a shared target's orphans as usual."""
    a, shared = _branches_sharing_a_target(pytester, monkeypatch)

    result = _run_in(pytester, monkeypatch, a, "--ditto-prune-dry-run")

    assert result.ret == 0
    result.stderr.fnmatch_lines(["*would prune*"])
    assert any("test_new" in p.name for p in shared.iterdir())


def test_prune_still_deletes_from_a_checkout_local_target(pytester, tmp_path_factory):
    """A file:// target inside the rootdir is this checkout's own, so its
    orphans are deleted while a shared target's are refused in the same run."""
    shared = tmp_path_factory.mktemp("shared")  # outside the rootdir
    module = f"""
import ditto

def test_local(snapshot):
    snapshot(1, key="a")

def test_local_gone(snapshot):
    snapshot(2, key="b")

@ditto.record("json", target="file://{shared}")
def test_remote(snapshot):
    snapshot(3, key="c")

@ditto.record("json", target="file://{shared}")
def test_remote_gone(snapshot):
    snapshot(4, key="d")
"""
    pytester.makepyfile(test_mod=module)
    pytester.runpytest_subprocess().assert_outcomes(passed=4)
    pytester.makepyfile(
        test_mod=module.replace("def test_local_gone", "def _local_gone").replace(
            "def test_remote_gone", "def _remote_gone"
        )
    )
    pytester.runpytest_subprocess("--ditto-lock").assert_outcomes(passed=2)

    result = pytester.runpytest_subprocess("--ditto-prune")

    assert result.ret != 0
    assert not any("test_local_gone" in f for f in _backend_files(pytester))
    assert any("test_local@" in f for f in _backend_files(pytester))
    assert any("test_remote_gone" in p.name for p in shared.iterdir())
