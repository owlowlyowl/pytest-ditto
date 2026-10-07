import dataclasses
from collections.abc import Iterator

import pytest

from ditto.plugin._options import (
    RUN_OPTIONS,
    PruneMode,
    RunOptions,
    read_run_options,
    run_options,
)
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

    expected = SnapshotMode.UPDATE
    assert actual == expected


class _CommandLine:
    """A stand-in for `pytest.Config` exposing only the given ditto options."""

    def __init__(self, **options: object) -> None:
        self._options = {
            f"--ditto-{name.replace('_', '-')}": v for name, v in options.items()
        }

    def getoption(self, name: str, default: object = None) -> object:
        return self._options.get(name, default)


@pytest.mark.parametrize("writer", ["update", "lock", "prune", "prune_dry_run"])
def test_rejects_verify_combined_with_an_option_that_writes(writer: str) -> None:
    """`--ditto-verify` is read-only, so combining it with a writing option fails."""
    command_line = _CommandLine(verify=True, **{writer: True})

    with pytest.raises(pytest.UsageError, match="--ditto-verify is read-only"):
        read_run_options(command_line)  # type: ignore[arg-type]


def test_rejects_prune_combined_with_prune_dry_run() -> None:
    """Pruning and a prune dry run cannot be requested together."""
    command_line = _CommandLine(prune=True, prune_dry_run=True)

    with pytest.raises(pytest.UsageError, match="cannot be combined"):
        read_run_options(command_line)  # type: ignore[arg-type]


def test_reads_dry_run_prune_with_update_mode() -> None:
    """Compatible flags map to their snapshot and prune modes."""
    command_line = _CommandLine(update=True, prune_dry_run=True)

    actual = read_run_options(command_line)  # type: ignore[arg-type]

    expected = RunOptions(
        snapshot_mode=SnapshotMode.UPDATE,
        rebuild_lock=False,
        prune=PruneMode.DRY_RUN,
        introspect_path="",
    )
    assert actual == expected
