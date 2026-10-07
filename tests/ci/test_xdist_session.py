"""The pytest-xdist support boundary, exercised against real distributed runs.

Snapshot recording and comparison run on the workers, so they work under
distribution. Verify, lock and prune need the whole run's observations in one
process, so they are rejected as a usage error before any test runs.
"""

import json

import pytest

pytest.importorskip("xdist")

pytest_plugins = ["pytester"]

TEST_MODULE = """
def test_alpha(snapshot):
    assert snapshot(1, key="a") == 1

def test_beta(snapshot):
    assert snapshot(2, key="b") == 2
"""

GAMMA_TEST = """
def test_gamma(snapshot):
    assert snapshot(3, key="c") == 3
"""

# `-n` is the usual way to distribute, but xdist also distributes whenever a
# distribution mode and worker specs are given directly.
DISTRIBUTION_ARGS = pytest.mark.parametrize(
    "dist_args",
    [("-n", "2"), ("--dist=load", "--tx=2*popen")],
    ids=["numprocesses", "dist-tx"],
)

SINGLE_PROCESS_MODES = pytest.mark.parametrize(
    "flag",
    ["--ditto-verify", "--ditto-lock", "--ditto-prune", "--ditto-prune-dry-run"],
)


def _seed(pytester):
    """Record snapshots and ditto.lock with a single-process run."""
    pytester.makepyfile(test_mod=TEST_MODULE)
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=2)


def _snapshot_files(pytester):
    return sorted(p.name for p in (pytester.path / ".ditto").iterdir())


def _delete_alpha_snapshot(pytester):
    next(
        p for p in (pytester.path / ".ditto").iterdir() if "test_alpha" in p.name
    ).unlink()


@DISTRIBUTION_ARGS
def test_records_snapshots_under_distribution(pytester, dist_args):
    """Workers write the snapshots each test records."""
    pytester.makepyfile(test_mod=TEST_MODULE)

    result = pytester.runpytest_subprocess(*dist_args)

    result.assert_outcomes(passed=2)
    assert len(_snapshot_files(pytester)) == 2


def test_compares_against_stored_snapshots_under_distribution(pytester, monkeypatch):
    """A value that no longer matches its stored snapshot fails on a worker."""
    # The edit below keeps the module's size, and a fast run keeps its mtime, so
    # the cached bytecode from the seeding run would still look current.
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    _seed(pytester)
    pytester.makepyfile(
        test_mod=TEST_MODULE.replace(
            'snapshot(1, key="a") == 1', 'snapshot(9, key="a") == 9'
        )
    )

    result = pytester.runpytest_subprocess("-n", "2")

    result.assert_outcomes(passed=1, failed=1)


@DISTRIBUTION_ARGS
def test_plain_run_warns_that_the_lock_is_not_maintained(pytester, dist_args):
    """An ordinary distributed run passes but says ditto.lock was not updated."""
    pytester.makepyfile(test_mod=TEST_MODULE)

    result = pytester.runpytest_subprocess(*dist_args)

    assert result.ret == 0
    result.stdout.fnmatch_lines(["*ditto.lock is not maintained under pytest-xdist*"])
    assert not (pytester.path / "ditto.lock").exists()


def test_session_report_is_not_rendered_under_distribution(pytester):
    """No process saw the whole run, so no (partial or empty) report is printed."""
    pytester.makepyfile(test_mod=TEST_MODULE)

    result = pytester.runpytest_subprocess("-n", "2")

    assert "ditto snapshot report" not in result.stderr.str()


@DISTRIBUTION_ARGS
def test_verify_is_rejected_under_distribution_when_a_snapshot_is_missing(
    pytester, dist_args
):
    """Verify is refused under distribution instead of passing unchecked."""
    _seed(pytester)
    _delete_alpha_snapshot(pytester)

    result = pytester.runpytest_subprocess("--ditto-verify", *dist_args)

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(["*ditto: --ditto-verify needs a single process*"])


@DISTRIBUTION_ARGS
@SINGLE_PROCESS_MODES
def test_single_process_mode_is_rejected_before_any_test_runs(
    pytester, flag, dist_args
):
    """A refused mode runs no tests, so it writes no snapshots and no lock."""
    _seed(pytester)
    lock_path = pytester.path / "ditto.lock"
    data = json.loads(lock_path.read_text())
    target = next(iter(data["targets"].values()))
    # Make test_beta's snapshot an orphan that prune would otherwise delete.
    target["entries"] = [e for e in target["entries"] if "test_beta" not in e["nodeid"]]
    lock_path.write_text(json.dumps(data))
    # A new test whose snapshot would be recorded if any test ran.
    pytester.makepyfile(test_mod=TEST_MODULE + GAMMA_TEST)
    lock_before = lock_path.read_text()
    snapshots_before = _snapshot_files(pytester)

    result = pytester.runpytest_subprocess(flag, *dist_args)

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines([f"*ditto: {flag} needs a single process*"])
    assert _snapshot_files(pytester) == snapshots_before
    assert lock_path.read_text() == lock_before


def test_verify_still_runs_with_n_0(pytester):
    """-n 0 is a single-process run, so verify checks the backend as usual."""
    _seed(pytester)
    _delete_alpha_snapshot(pytester)

    result = pytester.runpytest_subprocess("--ditto-verify", "-n", "0")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["*missing (recorded in lock, absent from backend)*"])


def test_verify_still_runs_without_xdist(pytester):
    """With xdist disabled there is no distribution to detect."""
    _seed(pytester)
    _delete_alpha_snapshot(pytester)

    result = pytester.runpytest_subprocess("--ditto-verify", "-p", "no:xdist")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["*missing (recorded in lock, absent from backend)*"])
