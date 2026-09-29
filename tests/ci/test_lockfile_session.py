import json
import types

import pytest

from ditto.plugin._lock import keeps_entry
from ditto.plugin._options import xdist_is_distributing
from ditto.plugin._session import CollectionRecord

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


# ── Rebuilds keep the entries of tests that didn't run (#156) ─────────────────

SKIPPABLE_MODULE = """
import os
import pytest

def test_alpha(snapshot):
    assert snapshot(1, key="a") == 1

@pytest.mark.skipif(os.environ.get("SKIP_BETA") == "1", reason="platform")
def test_beta(snapshot):
    assert snapshot(2, key="b") == 2
"""


def _beta_snapshot(pytester):
    return [p for p in (pytester.path / ".ditto").iterdir() if "test_beta" in p.name]


@pytest.mark.parametrize("rebuild", ["--ditto-lock", "--ditto-update"])
def test_a_skipped_test_keeps_its_entry_and_baseline_through_rebuild_and_prune(
    pytester, monkeypatch, rebuild
):
    """A test skipped on this machine keeps its lock entry through a rebuild, so
    the next prune doesn't delete its baseline."""
    pytester.makepyfile(test_mod=SKIPPABLE_MODULE)
    pytester.runpytest_subprocess("--ditto-lock").assert_outcomes(passed=2)
    monkeypatch.setenv("SKIP_BETA", "1")

    pytester.runpytest_subprocess(rebuild).assert_outcomes(passed=1, skipped=1)
    pruned = pytester.runpytest_subprocess("--ditto-prune")

    assert pruned.ret == 0
    assert any("test_beta" in n for n in _nodeids_in_lockfile(pytester))
    assert _beta_snapshot(pytester)


def test_a_deselected_test_keeps_its_entry(pytester):
    """A test left out with --deselect keeps its entry through a full rebuild."""
    pytester.makepyfile(test_mod=TEST_MODULE)
    pytester.runpytest_subprocess("--ditto-lock").assert_outcomes(passed=2)

    result = pytester.runpytest_subprocess(
        "--ditto-lock", "--deselect", "test_mod.py::test_beta"
    )

    assert result.ret == 0
    assert "test_mod.py::test_beta" in _nodeids_in_lockfile(pytester)


@pytest.mark.parametrize(
    "narrowing",
    [("--ignore", "test_beta_mod.py"), ("--ignore-glob", "*beta_mod.py")],
    ids=["ignore", "ignore-glob"],
)
def test_a_test_in_an_ignored_file_keeps_its_entry(pytester, narrowing):
    """A test in a file left out with --ignore or --ignore-glob keeps its entry
    through a full rebuild."""
    pytester.makepyfile(
        test_alpha_mod="def test_alpha(snapshot):\n    snapshot(1, key='a')\n",
        test_beta_mod="def test_beta(snapshot):\n    snapshot(2, key='b')\n",
    )
    pytester.runpytest_subprocess("--ditto-lock").assert_outcomes(passed=2)

    result = pytester.runpytest_subprocess("--ditto-lock", *narrowing)

    assert result.ret == 0
    assert "test_beta_mod.py::test_beta" in _nodeids_in_lockfile(pytester)


def test_a_test_skipped_partway_keeps_the_entries_it_did_not_reach(
    pytester, monkeypatch
):
    """A test that skips after some snapshots keeps the entries it didn't reach."""
    module = """
    import os
    import pytest

    def test_t(snapshot):
        snapshot(1, key="first")
        if os.environ.get("STOP") == "1":
            pytest.skip("stopped")
        snapshot(2, key="second")
    """
    pytester.makepyfile(test_mod=module)
    pytester.runpytest_subprocess("--ditto-lock").assert_outcomes(passed=1)
    monkeypatch.setenv("STOP", "1")

    pytester.runpytest_subprocess("--ditto-lock").assert_outcomes(skipped=1)

    data = json.loads((pytester.path / "ditto.lock").read_text())
    keys = {e["key"] for t in data["targets"].values() for e in t["entries"]}
    assert keys == {"first", "second"}


def test_a_passing_test_that_stops_using_a_key_loses_that_entry(pytester):
    """A test that passed is authoritative for its own entries."""
    pytester.makepyfile(test_mod=TEST_MODULE)
    pytester.runpytest_subprocess("--ditto-lock").assert_outcomes(passed=2)
    pytester.makepyfile(
        test_mod=TEST_MODULE.replace('snapshot(2, key="b") == 2', "True")
    )

    pytester.runpytest_subprocess("--ditto-lock").assert_outcomes(passed=2)

    data = json.loads((pytester.path / "ditto.lock").read_text())
    keys = {e["key"] for t in data["targets"].values() for e in t["entries"]}
    assert keys == {"a"}


@pytest.mark.parametrize(
    "skip",
    [
        "import pytest\npytest.skip('platform', allow_module_level=True)\n",
        "import pytest\npytest.importorskip('ditto_no_such_module')\n",
    ],
    ids=["skip", "importorskip"],
)
def test_a_module_skipped_at_collection_keeps_its_entries(pytester, skip):
    """A module skipped while being collected keeps its entries through a
    rebuild, and verifies cleanly once it runs again."""
    beta = "def test_beta(snapshot):\n    snapshot(2, key='b')\n"
    pytester.makepyfile(
        test_alpha_mod="def test_alpha(snapshot):\n    snapshot(1, key='a')\n",
        test_beta_mod=beta,
    )
    pytester.runpytest_subprocess("--ditto-lock").assert_outcomes(passed=2)
    pytester.makepyfile(test_beta_mod=skip + beta)

    result = pytester.runpytest_subprocess("--ditto-lock")

    assert result.ret == 0
    assert "test_beta_mod.py::test_beta" in _nodeids_in_lockfile(pytester)
    pytester.makepyfile(test_beta_mod=beta)
    assert pytester.runpytest_subprocess("--ditto-verify").ret == 0


def test_a_test_in_a_directory_matched_by_ignore_glob_keeps_its_entry(pytester):
    """--ignore-glob can match a directory, which pytest then doesn't enter;
    the tests inside it keep their entries in the target they share."""
    pytester.makeini(f"[pytest]\nditto_target = file://{pytester.path / 'snaps'}\n")
    pytester.makepyfile(
        test_alpha="def test_alpha(snapshot):\n    snapshot(1, key='a')\n"
    )
    platform = pytester.mkdir("platform_tests")
    (platform / "test_beta.py").write_text(
        "def test_beta(snapshot):\n    snapshot(2, key='b')\n"
    )
    pytester.runpytest_subprocess("--ditto-lock").assert_outcomes(passed=2)

    result = pytester.runpytest_subprocess(
        "--ditto-lock", "--ignore-glob", "*platform_tests"
    )

    assert result.ret == 0
    assert "platform_tests/test_beta.py::test_beta" in _nodeids_in_lockfile(pytester)


def test_a_test_in_a_file_a_conftest_ignores_keeps_its_entry(pytester, monkeypatch):
    """A file left out by a platform-dependent conftest `collect_ignore` keeps
    its entries."""
    pytester.makeconftest(
        "import os\n"
        "collect_ignore = ['test_beta_mod.py'] if os.environ.get('SKIP_BETA') else []\n"
    )
    pytester.makepyfile(
        test_alpha_mod="def test_alpha(snapshot):\n    snapshot(1, key='a')\n",
        test_beta_mod="def test_beta(snapshot):\n    snapshot(2, key='b')\n",
    )
    pytester.runpytest_subprocess("--ditto-lock").assert_outcomes(passed=2)
    monkeypatch.setenv("SKIP_BETA", "1")

    pytester.runpytest_subprocess("--ditto-lock").assert_outcomes(passed=1)

    assert "test_beta_mod.py::test_beta" in _nodeids_in_lockfile(pytester)


def test_a_deleted_module_still_loses_its_entries(pytester):
    """Recording what pytest ignored or skipped doesn't keep a deleted test."""
    pytester.makepyfile(
        test_alpha_mod="def test_alpha(snapshot):\n    snapshot(1, key='a')\n",
        test_beta_mod="def test_beta(snapshot):\n    snapshot(2, key='b')\n",
    )
    pytester.runpytest_subprocess("--ditto-lock").assert_outcomes(passed=2)
    (pytester.path / "test_beta_mod.py").unlink()

    pytester.runpytest_subprocess("--ditto-lock").assert_outcomes(passed=1)

    assert _nodeids_in_lockfile(pytester) == {"test_alpha_mod.py::test_alpha"}


NODE = "tests/unit/test_mod.py::TestC::test_m[a]"


@pytest.mark.parametrize(
    ("collection", "kept"),
    [
        (CollectionRecord(), False),
        (CollectionRecord(collected={NODE}), True),
        (CollectionRecord(collected={NODE}, passed={NODE}), False),
        (CollectionRecord(uncollected={""}), True),
        (CollectionRecord(uncollected={"tests"}), True),
        (CollectionRecord(uncollected={"tests/unit/test_mod.py"}), True),
        (CollectionRecord(uncollected={"tests/unit/test_mod.py::TestC"}), True),
        (CollectionRecord(uncollected={"tests/un"}), False),
        (CollectionRecord(uncollected={"tests/unit/test_mod"}), False),
        (CollectionRecord(uncollected={"tests/other"}), False),
    ],
    ids=[
        "deleted",
        "collected",
        "passed",
        "root-ignored",
        "directory-ignored",
        "module-skipped",
        "class-skipped",
        "partial-directory-name",
        "partial-file-name",
        "sibling-directory",
    ],
)
def test_keeps_entry(collection, kept):
    """An entry is kept for a collected test that didn't pass, or one under
    something pytest left out, matched on whole node-id segments."""
    assert keeps_entry(NODE, collection) is kept
