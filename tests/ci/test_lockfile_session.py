import json
import types

from ditto.plugin import _xdist_is_distributing

pytest_plugins = ["pytester"]

TEST_MODULE = """
def test_alpha(snapshot):
    assert snapshot(1, key="a") == 1

def test_beta(snapshot):
    assert snapshot(2, key="b") == 2
"""


def _nodeids_in_lockfile(pytester):
    data = json.loads((pytester.path / "ditto.lock").read_text())
    return {e["nodeid"] for t in data["targets"].values() for e in t["entries"]}


def test_creates_lockfile_entries_for_all_recorded_snapshots(pytester):
    """A normal run writes a lock entry for every snapshot it records."""
    pytester.makepyfile(test_mod=TEST_MODULE)

    result = pytester.runpytest_subprocess()

    result.assert_outcomes(passed=2)
    nodeids = _nodeids_in_lockfile(pytester)
    assert any("test_alpha" in n for n in nodeids)
    assert any("test_beta" in n for n in nodeids)


def test_partial_run_appends_new_entry_while_keeping_existing(pytester):
    """A new snapshot in a later run is merged in without dropping prior entries."""
    pytester.makepyfile(test_mod=TEST_MODULE)
    pytester.runpytest_subprocess()  # records alpha and beta

    # Add a third test and run only it: its entry must be appended into the
    # existing ditto.lock (proving a real merge), and beta must survive.
    pytester.makepyfile(
        test_mod=TEST_MODULE
        + """
def test_gamma(snapshot):
    assert snapshot(3, key="c") == 3
"""
    )
    pytester.runpytest_subprocess("-k", "test_gamma")

    nodeids = _nodeids_in_lockfile(pytester)
    assert any("test_beta" in n for n in nodeids)
    assert any("test_gamma" in n for n in nodeids)


def _append_stale_entry(pytester):
    lock_path = pytester.path / "ditto.lock"
    data = json.loads(lock_path.read_text())
    target = next(iter(data["targets"].values()))
    target["entries"].append({
        "nodeid": "test_mod.py::test_removed",
        "key": "z",
        "recorder": "pkl",
    })
    lock_path.write_text(json.dumps(data))


def test_ditto_lock_removes_stale_entry_on_full_run(pytester):
    """A full --ditto-lock run rebuilds entries, dropping a stale one."""
    pytester.makepyfile(test_mod=TEST_MODULE)
    pytester.runpytest_subprocess()
    _append_stale_entry(pytester)

    result = pytester.runpytest_subprocess("--ditto-lock")

    result.assert_outcomes(passed=2)
    assert not any("test_removed" in n for n in _nodeids_in_lockfile(pytester))


def test_ditto_lock_does_not_rewrite_snapshot_values(pytester):
    """--ditto-lock leaves snapshot bytes untouched."""
    pytester.makepyfile(test_mod=TEST_MODULE)
    pytester.runpytest_subprocess()
    snap_dir = pytester.path / ".ditto"
    before = {p.name: p.read_bytes() for p in snap_dir.iterdir()}

    pytester.runpytest_subprocess("--ditto-lock")

    after = {p.name: p.read_bytes() for p in snap_dir.iterdir()}
    assert after == before


def test_ditto_lock_refuses_to_rebuild_on_filtered_run(pytester):
    """A filtered --ditto-lock run does not rebuild, so a stale entry survives."""
    pytester.makepyfile(test_mod=TEST_MODULE)
    pytester.runpytest_subprocess()
    _append_stale_entry(pytester)

    result = pytester.runpytest_subprocess("--ditto-lock", "-k", "test_alpha")

    assert result.ret != 0  # an explicit refusal fails the command
    assert any("test_removed" in n for n in _nodeids_in_lockfile(pytester))


def test_ditto_lock_preserves_unexercised_targets(pytester):
    """A rebuild only touches exercised targets, leaving others intact."""
    pytester.makepyfile(test_mod=TEST_MODULE)
    pytester.runpytest_subprocess()
    # Inject a target that no test in this run exercises.
    lock_path = pytester.path / "ditto.lock"
    data = json.loads(lock_path.read_text())
    data["targets"]["other/.ditto"] = {
        "scheme": "file",
        "entries": [
            {"nodeid": "other/test_x.py::test_x", "key": "k", "recorder": "pkl"}
        ],
    }
    lock_path.write_text(json.dumps(data))

    pytester.runpytest_subprocess("--ditto-lock")

    assert any("other/test_x.py::test_x" in n for n in _nodeids_in_lockfile(pytester))


def test_warns_when_lockfile_is_gitignored(pytester):
    """A gitignored ditto.lock is flagged because it must be committed."""
    pytester.makepyfile(test_mod=TEST_MODULE)
    (pytester.path / ".gitignore").write_text("ditto.lock\n")

    result = pytester.runpytest_subprocess()

    result.stdout.fnmatch_lines(["*ditto.lock*gitignore*"])


PHANTOM_MODULE = """
def test_phantom(snapshot):
    snapshot(lambda x: x, key="k")  # unpicklable -> write fails -> test errors
"""


def test_failed_snapshot_write_leaves_no_phantom_lock_entry(pytester):
    """A snapshot whose write fails must not leave an entry in ditto.lock."""
    pytester.makepyfile(test_mod=PHANTOM_MODULE)

    pytester.runpytest_subprocess()  # the snapshot write raises; the test fails

    lock = pytester.path / "ditto.lock"
    if lock.exists():
        assert not any("test_phantom" in n for n in _nodeids_in_lockfile(pytester))


def test_ditto_lock_refuses_path_narrowed_run(pytester):
    """--ditto-lock with a positional path arg refuses and does not truncate."""
    pytester.makepyfile(
        test_a="def test_a(snapshot):\n    assert snapshot(1, key='a') == 1\n",
        test_b="def test_b(snapshot):\n    assert snapshot(2, key='b') == 2\n",
    )
    pytester.runpytest_subprocess()  # full run records both test_a and test_b

    result = pytester.runpytest_subprocess("--ditto-lock", "test_a.py")

    assert result.ret != 0  # path-narrowed rebuild is refused
    nodeids = _nodeids_in_lockfile(pytester)
    assert any("test_a" in n for n in nodeids)
    assert any("test_b" in n for n in nodeids)  # NOT truncated


def test_ditto_lock_replaces_corrupt_lock_file(pytester):
    """--ditto-lock rebuilds a corrupt ditto.lock instead of leaving it broken."""
    pytester.makepyfile(test_mod=TEST_MODULE)
    pytester.runpytest_subprocess()  # valid lock with alpha + beta
    (pytester.path / "ditto.lock").write_text("{not json")  # corrupt it

    result = pytester.runpytest_subprocess("--ditto-lock")

    assert result.ret == 0
    nodeids = _nodeids_in_lockfile(pytester)  # raises if still corrupt
    assert any("test_alpha" in n for n in nodeids)
    assert any("test_beta" in n for n in nodeids)


def test_xdist_distribution_detected_when_numprocesses_set():
    """A positive -n value marks the run as xdist-distributed."""
    config = types.SimpleNamespace(option=types.SimpleNamespace(numprocesses=4))

    assert _xdist_is_distributing(config) is True


def test_no_xdist_distribution_when_numprocesses_absent_or_zero():
    """No -n (or -n0) is a single-process run."""
    absent = types.SimpleNamespace(option=types.SimpleNamespace())
    zero = types.SimpleNamespace(option=types.SimpleNamespace(numprocesses=0))

    assert _xdist_is_distributing(absent) is False
    assert _xdist_is_distributing(zero) is False
