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
def test_run_stops_before_collection_listing_each_contract_problem(
    pytester: pytest.Pytester,
) -> None:
    """A pytest run lists every contract problem and collects no tests."""
    pytester.makepyfile(test_mod=CONTRACT_MODULE)

    result = pytester.runpytest_subprocess()

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines([
        "*ditto: the installed recorder plugins break the plugin contract:",
        "*Recorder name 'tab.csv' is registered more than once, by plug-a 1.0, "
        "plug-b 2.0.*",
        "*old-plug 0.1 uses the 1.x plugin contract; install old-plug>=2.0.",
    ])
    assert not (pytester.path / ".ditto").exists()


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


@pytest.fixture
def unused_clashing_plugin(make_distribution, monkeypatch: pytest.MonkeyPatch):
    """Install a plugin that registers core's `json` name, and return its root.

    Importing the plugin's module leaves an `imported` file in the root.
    """
    (ep,) = make_distribution(
        "plug-c", "1.0", {"ditto_recorders": {"json": "clashmod:recorder"}}
    )
    root = ep.dist.locate_file("")
    (root / "clashmod.py").write_text(
        "import pathlib\n"
        "pathlib.Path(__file__).with_name('imported').touch()\n"
        "from ditto.recorders import Recorder\n"
        "recorder = Recorder(dumps=bytes, loads=bytes)\n"
    )
    monkeypatch.setenv(
        "PYTHONPATH",
        os.pathsep.join([str(root), *filter(None, [os.environ.get("PYTHONPATH")])]),
    )
    return root


def test_unused_clashing_plugin_stops_the_run_without_being_imported(
    pytester: pytest.Pytester, unused_clashing_plugin
) -> None:
    """A clash with core is found from metadata before any snapshot is written."""
    pytester.makepyfile(
        test_mod="""
        import ditto


        @ditto.yaml
        def test_uses_yaml(snapshot):
            assert snapshot(1, key="k") == 1
        """
    )

    result = pytester.runpytest_subprocess()

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines([
        "*Recorder name 'json' is registered more than once, by plug-c 1.0, "
        "pytest-ditto *"
    ])
    assert not (pytester.path / ".ditto").exists()
    assert not (unused_clashing_plugin / "imported").exists()


@pytest.mark.usefixtures("unused_clashing_plugin")
def test_recorders_reports_a_clash_without_importing_plugins() -> None:
    """`ditto recorders` reports a clash found from metadata alone."""
    result = subprocess.run(
        [sys.executable, "-c", "from ditto.cli import cli; cli()", "recorders"],
        capture_output=True,
        text=True,
        env={**os.environ, "COLUMNS": "200"},
    )

    assert "1 plugin contract problem(s)" in result.stdout
