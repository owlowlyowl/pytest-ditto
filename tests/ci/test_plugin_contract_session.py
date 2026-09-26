"""Plugin contract problems in a real pytest run and in `ditto doctor`."""

import os
import subprocess
import sys

import pytest

pytest_plugins = ["pytester"]

_JSON = "ditto.recorders._json:json"

CONTRACT_MODULE = """
import ditto


@ditto.tab.csv
def test_uses_conflicted_recorder(snapshot):
    snapshot(1, key="k")


def test_uses_default_recorder(snapshot):
    assert snapshot(1, key="k") == 1
"""


@pytest.fixture
def conflicting_plugins(make_distribution, monkeypatch: pytest.MonkeyPatch) -> None:
    """Install two plugins registering `tab.csv` and one on the 1.x contract."""
    installed = [
        make_distribution("plug-a", "1.0", {"ditto_recorders": {"tab.csv": _JSON}}),
        make_distribution("plug-b", "2.0", {"ditto_recorders": {"tab.csv": _JSON}}),
        make_distribution("old-plug", "0.1", {"ditto_marks": {"old": "m:marks"}}),
    ]
    roots = [str(eps[0].dist.locate_file("")) for eps in installed]
    monkeypatch.setenv(
        "PYTHONPATH",
        os.pathsep.join([*roots, *filter(None, [os.environ.get("PYTHONPATH")])]),
    )


@pytest.mark.usefixtures("conflicting_plugins")
def test_run_warns_about_each_contract_problem(pytester: pytest.Pytester) -> None:
    """A pytest run reports every contract problem as a DittoWarning."""
    pytester.makepyfile(test_mod=CONTRACT_MODULE)

    result = pytester.runpytest_subprocess()

    result.stdout.fnmatch_lines([
        "*DittoWarning: Recorder name 'tab.csv' is registered more than once, "
        "by plug-a 1.0, plug-b 2.0.*",
        "*DittoWarning: old-plug 0.1 uses the 1.x plugin contract; install "
        "old-plug>=2.0.*",
    ])


@pytest.mark.usefixtures("conflicting_plugins")
def test_run_fails_only_the_test_using_a_conflicted_recorder(
    pytester: pytest.Pytester,
) -> None:
    """The conflicted recorder errors at setup; other tests are unaffected."""
    pytester.makepyfile(test_mod=CONTRACT_MODULE)

    result = pytester.runpytest_subprocess()

    result.assert_outcomes(passed=1, errors=1)
    result.stdout.fnmatch_lines(["*DittoRecorderConflictError: *'tab.csv'*"])


@pytest.mark.usefixtures("conflicting_plugins")
def test_doctor_fails_on_contract_problems() -> None:
    """`ditto doctor` fails, listing each contract problem."""
    result = subprocess.run(
        [sys.executable, "-c", "from ditto.cli import cli; cli()", "doctor"],
        capture_output=True,
        text=True,
        env={**os.environ, "COLUMNS": "200"},
    )

    assert result.returncode == 1
    assert "registered more than once, by plug-a 1.0, plug-b 2.0" in result.stdout
    assert "old-plug 0.1 uses the 1.x plugin contract" in result.stdout


def test_recorders_reports_an_identifier_collision(
    make_distribution, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ditto recorders` reports a collision only found by loading recorders."""
    (ep,) = make_distribution(
        "plug-c", "1.0", {"ditto_recorders": {"clash.json": "clashmod:recorder"}}
    )
    root = ep.dist.locate_file("")
    (root / "clashmod.py").write_text(
        "from ditto.recorders import Recorder\n"
        "recorder = Recorder(identifier='json', save=print, load=print)\n"
    )
    monkeypatch.setenv(
        "PYTHONPATH",
        os.pathsep.join([str(root), *filter(None, [os.environ.get("PYTHONPATH")])]),
    )

    result = subprocess.run(
        [sys.executable, "-c", "from ditto.cli import cli; cli()", "recorders"],
        capture_output=True,
        text=True,
        env={**os.environ, "COLUMNS": "200"},
    )

    assert "1 plugin contract problem(s)" in result.stdout
