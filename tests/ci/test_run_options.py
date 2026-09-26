import dataclasses
from collections.abc import Iterator

import pytest

from ditto.plugin._options import RUN_OPTIONS, read_run_options, run_options
from ditto.snapshot import SnapshotMode


@pytest.fixture
def update_mode_stored(pytestconfig: pytest.Config) -> Iterator[None]:
    """Store update-mode options for this run, restoring the originals after."""
    original = run_options(pytestconfig)
    pytestconfig.stash[RUN_OPTIONS] = dataclasses.replace(
        original, snapshot_mode=SnapshotMode.UPDATE
    )
    yield
    pytestconfig.stash[RUN_OPTIONS] = original


def test_stores_run_options_parsed_from_the_command_line(
    pytestconfig: pytest.Config,
) -> None:
    """The stored options match a fresh parse of this run's command line."""
    actual = run_options(pytestconfig)

    expected = read_run_options(pytestconfig)
    assert actual == expected


@pytest.mark.usefixtures("update_mode_stored")
def test_snapshot_fixture_uses_the_stored_run_options(
    request: pytest.FixtureRequest,
) -> None:
    """The fixture takes its mode from the stored options, not a re-read of flags."""
    actual = request.getfixturevalue("snapshot").mode

    assert actual is SnapshotMode.UPDATE
