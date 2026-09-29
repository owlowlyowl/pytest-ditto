import json
import types

import pytest

from ditto.plugin._options import xdist_is_distributing

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


def test_ditto_update_full_run_reconciles_lock(pytester):
    """A full --ditto-update drops a deleted test's stale entry from the lock."""
    pytester.makepyfile(test_mod=TEST_MODULE)
    pytester.runpytest_subprocess()  # records alpha + beta
    _append_stale_entry(pytester)

    result = pytester.runpytest_subprocess("--ditto-update")

    result.assert_outcomes(passed=2)
    assert not any("test_removed" in n for n in _nodeids_in_lockfile(pytester))


def test_ditto_update_filtered_run_appends_without_removing(pytester):
    """A filtered --ditto-update appends only, so a stale entry survives."""
    pytester.makepyfile(test_mod=TEST_MODULE)
    pytester.runpytest_subprocess()
    _append_stale_entry(pytester)

    pytester.runpytest_subprocess("--ditto-update", "-k", "test_alpha")

    assert any("test_removed" in n for n in _nodeids_in_lockfile(pytester))


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

    result = pytester.runpytest_subprocess()

    assert result.ret != 0  # the write raised, so the scenario actually triggered
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


def _xdist_config(**option):
    return types.SimpleNamespace(option=types.SimpleNamespace(**option))


@pytest.mark.parametrize(
    "option",
    [
        # -n 4 and -n auto, after xdist has normalised them.
        {"numprocesses": 4, "dist": "load", "tx": ["popen"] * 4},
        # --dist=load --tx=2*popen, which leaves numprocesses unset.
        {"numprocesses": None, "dist": "load", "tx": ["2*popen"]},
    ],
    ids=["numprocesses", "dist-tx"],
)
def test_xdist_distribution_detected(option):
    """A distribution mode with worker specs marks the run as distributed."""
    assert xdist_is_distributing(_xdist_config(**option)) is True


@pytest.mark.parametrize(
    "option",
    [
        {},  # xdist not installed
        {"numprocesses": None, "dist": "no", "tx": []},  # no -n
        {"numprocesses": 0, "dist": "no", "tx": []},  # -n 0
        {"numprocesses": None, "dist": "load", "tx": []},  # --dist with no workers
        {"dist": "load", "tx": ["popen"] * 2, "collectonly": True},
    ],
    ids=["no-xdist", "no-n", "n0", "dist-without-tx", "collect-only"],
)
def test_no_xdist_distribution(option):
    """Without both a distribution mode and worker specs, the run is local."""
    assert xdist_is_distributing(_xdist_config(**option)) is False


NESTED_SESSION_MODULE = '''
import ditto

pytest_plugins = ["pytester"]


def test_a_outer(snapshot):
    assert snapshot(1, key="outer") == 1


def test_b_nested(pytester):
    pytester.makepyfile(test_inner="""
        import ditto

        @ditto.record("json", target="memory://nested")
        def test_inner(snapshot):
            assert snapshot(2, key="inner") == 2
    """)
    pytester.runpytest().assert_outcomes(passed=1)
'''


@pytest.mark.parametrize(
    "args",
    [
        pytest.param((), id="full-run"),
        pytest.param(("-k", "a_outer or b_nested"), id="filtered-run"),
    ],
)
def test_nested_in_process_session_does_not_leak_into_outer_lockfile(pytester, args):
    """An in-process pytester session run from inside a test keeps its own ditto
    state: its snapshots never reach the outer session's ditto.lock, and the outer
    session's own observations survive it (#115)."""
    pytester.makepyfile(test_outer=NESTED_SESSION_MODULE)

    result = pytester.runpytest_subprocess(*args)

    result.assert_outcomes(passed=2)
    data = json.loads((pytester.path / "ditto.lock").read_text())
    entries = {
        (e["nodeid"], e["key"]) for t in data["targets"].values() for e in t["entries"]
    }
    assert entries == {("test_outer.py::test_a_outer", "outer")}


# ── A failed rebuild fails the run (#159) ─────────────────────────────────────


def _make_lock_unwritable(pytester):
    """Replace ditto.lock with a directory, which can be neither read nor written."""
    lock = pytester.path / "ditto.lock"
    lock.unlink(missing_ok=True)
    lock.mkdir()


@pytest.mark.parametrize("rebuild", ["--ditto-lock", "--ditto-update"])
def test_a_rebuild_that_cannot_write_the_lock_fails_the_run(pytester, rebuild):
    """`ditto lock` or a full `ditto update` that can't write the lock exits
    non-zero and says why, even with warnings filtered out."""
    pytester.makepyfile(test_mod=TEST_MODULE)
    pytester.runpytest_subprocess().assert_outcomes(passed=2)
    _make_lock_unwritable(pytester)

    result = pytester.runpytest_subprocess(rebuild, "-W", "ignore::UserWarning")

    result.assert_outcomes(passed=2)
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["*ditto: failed to write ditto.lock*"])


def test_an_ordinary_run_that_cannot_append_to_the_lock_only_warns(pytester):
    """A plain run still passes when the lock can't be written; it warns."""
    pytester.makepyfile(test_mod=TEST_MODULE)
    _make_lock_unwritable(pytester)

    result = pytester.runpytest_subprocess()

    assert result.ret == pytest.ExitCode.OK
    result.stdout.fnmatch_lines(["*DittoWarning: Failed to write ditto.lock*"])
