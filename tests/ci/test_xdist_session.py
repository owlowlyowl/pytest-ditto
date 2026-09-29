"""The pytest-xdist support boundary, exercised against real `-n 2` runs.

Snapshot recording and comparison run on the workers, so they work under
distribution. Verify, lock and prune need the whole run's observations in one
process, so they refuse and fail the run.
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


def _seed(pytester):
    """Record snapshots and ditto.lock with a single-process run."""
    pytester.makepyfile(test_mod=TEST_MODULE)
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=2)


def _snapshot_files(pytester):
    return sorted(p.name for p in (pytester.path / ".ditto").iterdir())


def test_records_snapshots_under_distribution(pytester):
    """Workers write the snapshots each test records."""
    pytester.makepyfile(test_mod=TEST_MODULE)

    result = pytester.runpytest_subprocess("-n", "2")

    result.assert_outcomes(passed=2)
    assert len(_snapshot_files(pytester)) == 2


def test_compares_against_stored_snapshots_under_distribution(pytester):
    """A value that no longer matches its stored snapshot fails on a worker."""
    _seed(pytester)
    pytester.makepyfile(
        test_mod=TEST_MODULE.replace(
            'snapshot(1, key="a") == 1', 'snapshot(9, key="a") == 9'
        )
    )

    result = pytester.runpytest_subprocess("-n", "2")

    result.assert_outcomes(passed=1, failed=1)


def test_plain_run_warns_that_the_lock_is_not_maintained(pytester):
    """An ordinary distributed run passes but says ditto.lock was not updated."""
    pytester.makepyfile(test_mod=TEST_MODULE)

    result = pytester.runpytest_subprocess("-n", "2")

    assert result.ret == 0
    result.stdout.fnmatch_lines(["*ditto.lock is not maintained under pytest-xdist*"])
    assert not (pytester.path / "ditto.lock").exists()


def test_session_report_is_not_rendered_under_distribution(pytester):
    """No process saw the whole run, so no (partial or empty) report is printed."""
    pytester.makepyfile(test_mod=TEST_MODULE)

    result = pytester.runpytest_subprocess("-n", "2")

    assert "ditto snapshot report" not in result.stderr.str()


def test_verify_fails_under_distribution_even_when_a_snapshot_is_missing(pytester):
    """Verify refuses under -n instead of passing without checking anything."""
    _seed(pytester)
    next(
        p for p in (pytester.path / ".ditto").iterdir() if "test_alpha" in p.name
    ).unlink()

    result = pytester.runpytest_subprocess("--ditto-verify", "-n", "2")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["*ditto: --ditto-verify needs a single process*"])


def test_verify_fails_under_distribution_when_the_backend_matches(pytester):
    """Verify refuses under -n even when there is no drift to find."""
    _seed(pytester)

    result = pytester.runpytest_subprocess("--ditto-verify", "-n", "2")

    assert result.ret == pytest.ExitCode.TESTS_FAILED


def test_lock_fails_under_distribution_and_leaves_the_lock_alone(pytester):
    """--ditto-lock refuses under -n and does not rewrite ditto.lock."""
    _seed(pytester)
    lock_path = pytester.path / "ditto.lock"
    before = lock_path.read_text()

    result = pytester.runpytest_subprocess("--ditto-lock", "-n", "2")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["*ditto: --ditto-lock needs a single process*"])
    assert lock_path.read_text() == before


@pytest.mark.parametrize("flag", ["--ditto-prune", "--ditto-prune-dry-run"])
def test_prune_fails_under_distribution_and_deletes_nothing(pytester, flag):
    """Prune refuses under -n and leaves an orphan in place."""
    _seed(pytester)
    lock_path = pytester.path / "ditto.lock"
    data = json.loads(lock_path.read_text())
    target = next(iter(data["targets"].values()))
    target["entries"] = [e for e in target["entries"] if "test_beta" not in e["nodeid"]]
    lock_path.write_text(json.dumps(data))
    before = _snapshot_files(pytester)

    result = pytester.runpytest_subprocess(flag, "-n", "2")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines([f"*ditto: {flag} needs a single process*"])
    assert _snapshot_files(pytester) == before


def test_verify_still_runs_with_n_0(pytester):
    """-n 0 is a single-process run, so verify checks the backend as usual."""
    _seed(pytester)
    next(
        p for p in (pytester.path / ".ditto").iterdir() if "test_alpha" in p.name
    ).unlink()

    result = pytester.runpytest_subprocess("--ditto-verify", "-n", "0")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["*missing (recorded in lock, absent from backend)*"])
