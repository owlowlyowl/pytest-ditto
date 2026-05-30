import json

pytest_plugins = ["pytester"]

TEST_MODULE = '''
def test_alpha(snapshot):
    assert snapshot(1, key="a") == 1

def test_beta(snapshot):
    assert snapshot(2, key="b") == 2
'''


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
    """A later run that records a new snapshot merges it in without dropping prior entries."""
    pytester.makepyfile(test_mod=TEST_MODULE)
    pytester.runpytest_subprocess()  # records alpha and beta

    # Add a third test and run only it: its entry must be appended into the
    # existing ditto.lock (proving a real merge), and beta must survive.
    pytester.makepyfile(
        test_mod=TEST_MODULE
        + '''
def test_gamma(snapshot):
    assert snapshot(3, key="c") == 3
'''
    )
    pytester.runpytest_subprocess("-k", "test_gamma")

    nodeids = _nodeids_in_lockfile(pytester)
    assert any("test_beta" in n for n in nodeids)
    assert any("test_gamma" in n for n in nodeids)
