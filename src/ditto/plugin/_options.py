from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import cast

import pytest

from ditto.exceptions import DittoAmbiguousTargetError
from ditto.snapshot import SnapshotMode


__all__ = (
    "StorageOptions",
    "StorageOptionsByScheme",
    "PruneMode",
    "RunOptions",
    "RUN_OPTIONS",
    "read_run_options",
    "run_options",
    "add_options",
    "validate_ini_options",
    "validate_target_config",
    "get_optional_fixturevalue",
    "get_storage_options",
    "is_xdist_worker",
    "xdist_is_distributing",
    "reject_single_process_modes_under_xdist",
)


StorageOptions = dict[str, object]
StorageOptionsByScheme = dict[str, StorageOptions]


class PruneMode(Enum):
    """Whether the session prunes orphaned snapshots when it finishes."""

    OFF = "off"
    DRY_RUN = "dry-run"
    DELETE = "delete"


@dataclass(frozen=True)
class RunOptions:
    """The ditto command-line options for one run.

    Read and validated once, in `pytest_configure`, and stored on `config.stash`
    under `RUN_OPTIONS`; `run_options` returns that instance.

    Attributes
    ----------
    snapshot_mode : SnapshotMode
        `UPDATE` with `--ditto-update`, `VERIFY` with `--ditto-verify`, otherwise
        `RECORD`.
    rebuild_lock : bool
        `--ditto-lock`: rebuild `ditto.lock` from this run.
    prune : PruneMode
        `--ditto-prune` (`DELETE`) or `--ditto-prune-dry-run` (`DRY_RUN`).
    introspect_path : str
        `--ditto-introspect`: where to write the backend manifest, or `""`.
    """

    snapshot_mode: SnapshotMode
    rebuild_lock: bool
    prune: PruneMode
    introspect_path: str


RUN_OPTIONS = pytest.StashKey[RunOptions]()


def run_options(config: pytest.Config) -> RunOptions:
    """Return the run's options, as stored by `pytest_configure`."""
    return config.stash[RUN_OPTIONS]


def read_run_options(config: pytest.Config) -> RunOptions:
    """Read and validate ditto's command-line options from `config`.

    Raises
    ------
    pytest.UsageError
        When `--ditto-verify` is combined with an option that writes, or
        `--ditto-prune` with `--ditto-prune-dry-run`.
    """
    verify = bool(config.getoption("--ditto-verify", default=False))
    update = bool(config.getoption("--ditto-update", default=False))
    rebuild_lock = bool(config.getoption("--ditto-lock", default=False))
    prune = bool(config.getoption("--ditto-prune", default=False))
    dry_run = bool(config.getoption("--ditto-prune-dry-run", default=False))

    if verify and (update or rebuild_lock or prune or dry_run):
        raise pytest.UsageError(
            "--ditto-verify is read-only and cannot be combined with "
            "--ditto-update, --ditto-lock, --ditto-prune, or "
            "--ditto-prune-dry-run."
        )
    if prune and dry_run:
        raise pytest.UsageError(
            "--ditto-prune and --ditto-prune-dry-run cannot be combined."
        )

    if verify:
        snapshot_mode = SnapshotMode.VERIFY
    elif update:
        snapshot_mode = SnapshotMode.UPDATE
    else:
        snapshot_mode = SnapshotMode.RECORD

    if prune:
        prune_mode = PruneMode.DELETE
    elif dry_run:
        prune_mode = PruneMode.DRY_RUN
    else:
        prune_mode = PruneMode.OFF

    return RunOptions(
        snapshot_mode=snapshot_mode,
        rebuild_lock=rebuild_lock,
        prune=prune_mode,
        introspect_path=str(config.getoption("--ditto-introspect", default="")),
    )


def add_options(parser: pytest.Parser) -> None:
    """Declare ditto's command-line options and ini values."""
    group = parser.getgroup("ditto")
    group.addoption(
        "--ditto-update",
        action="store_true",
        default=False,
        help="Overwrite all existing snapshots with current test values.",
    )
    group.addoption(
        "--ditto-prune",
        action="store_true",
        default=False,
        help="After the session, delete backend snapshots not recorded in ditto.lock.",
    )
    group.addoption(
        "--ditto-prune-dry-run",
        action="store_true",
        default=False,
        help=(
            "Report snapshots that --ditto-prune would delete (backend keys not in "
            "ditto.lock), without deleting anything."
        ),
    )
    group.addoption(
        "--ditto-introspect",
        default="",
        metavar="PATH",
        help=(
            "Internal: resolve every test's backend, write a JSON manifest of "
            "stored snapshots to PATH, then skip pruning. Used by the ditto CLI "
            "to introspect backends. Combine with --setup-only."
        ),
    )
    group.addoption(
        "--ditto-lock",
        action="store_true",
        default=False,
        help=(
            "Rebuild ditto.lock from the snapshots exercised by this run, without "
            "rewriting snapshot values. Requires a full (unfiltered, passing) run."
        ),
    )
    group.addoption(
        "--ditto-verify",
        action="store_true",
        default=False,
        help=(
            "Read-only: fail the run if the live backend has drifted from "
            "ditto.lock (missing, orphan, or unrecorded snapshots)."
        ),
    )
    parser.addini(
        "ditto_target",
        help=(
            "Default snapshot storage URI for all tests in this project. "
            "Examples: 's3://my-bucket/ditto', 'file://.ditto'. "
            "Relative file:// paths resolve relative to the test file. "
            "Credentials come from the ditto_storage_options fixture."
        ),
        default="",
    )
    parser.addini(
        "ditto_target_profile",
        help=(
            "Default named target profile for all tests in this project. "
            "Must be a key defined in ditto_target_profiles or "
            "[tool.pytest-ditto.target_profiles] in pyproject.toml. "
            "Cannot be set alongside ditto_target."
        ),
        default="",
    )


def validate_ini_options(config: pytest.Config) -> None:
    """Raise `pytest.UsageError` for conflicting ditto ini values."""
    try:
        validate_target_config(config)
    except DittoAmbiguousTargetError as exc:
        raise pytest.UsageError(str(exc)) from exc


def validate_target_config(config: pytest.Config) -> None:
    """Raise if both ditto_target and ditto_target_profile are configured."""
    if config.getini("ditto_target") and config.getini("ditto_target_profile"):
        raise DittoAmbiguousTargetError(
            "Use either ditto_target or ditto_target_profile, not both."
        )


def get_optional_fixturevalue(
    request: pytest.FixtureRequest,
    name: str,
) -> object | None:
    """Return an optional fixture value without hiding dependency errors."""
    try:
        return request.getfixturevalue(name)
    except pytest.FixtureLookupError as exc:
        if exc.argname != name:
            raise
        return None


def get_storage_options(request: pytest.FixtureRequest) -> StorageOptionsByScheme:
    """Return per-scheme storage options from ditto_storage_options, or {}."""
    storage_options = get_optional_fixturevalue(request, "ditto_storage_options")
    if storage_options is None:
        return {}
    return cast(StorageOptionsByScheme, storage_options)


def is_xdist_worker(config: pytest.Config) -> bool:
    """True when running inside an xdist worker subprocess."""
    return hasattr(config, "workerinput")


def xdist_is_distributing(config: pytest.Config) -> bool:
    """True when pytest-xdist is distributing this run across worker processes.

    Under distribution the controller process (which runs `pytest_sessionfinish`
    and writes the lock) never executes test bodies, so its session tracker is
    empty and any lock write would be wrong (see #83).

    This is xdist's own test: a distribution mode other than "no" plus worker
    specs in `tx`. It covers `-n N`/`-n auto` as well as `--dist`/`--tx`,
    because by `pytest_configure` xdist has turned `-n N` into N `popen` specs
    and `-n 0` into `dist="no"`. xdist does not distribute a `--collect-only`
    run. Without xdist installed, none of these options exist.
    """
    option = config.option
    if getattr(option, "collectonly", False):
        return False
    return getattr(option, "dist", "no") != "no" and bool(getattr(option, "tx", None))


def reject_single_process_modes_under_xdist(
    config: pytest.Config, options: RunOptions
) -> None:
    """Raise `pytest.UsageError` for a mode that can't run under distribution.

    Verify, lock and prune need to observe the whole run in one process. Under
    distribution they would check or write nothing, so refuse them before any
    test runs rather than report a false success at session end.
    """
    if is_xdist_worker(config) or not xdist_is_distributing(config):
        return
    mode = _single_process_mode(options)
    if mode is not None:
        raise pytest.UsageError(
            f"ditto: {mode} needs a single process and cannot run under "
            "pytest-xdist distribution (-n, --dist/--tx); rerun it with -n 0."
        )


def _single_process_mode(options: RunOptions) -> str | None:
    """Name of the requested mode that needs to observe the whole run, if any."""
    if options.snapshot_mode is SnapshotMode.VERIFY:
        return "--ditto-verify"
    if options.rebuild_lock:
        return "--ditto-lock"
    match options.prune:
        case PruneMode.DELETE:
            return "--ditto-prune"
        case PruneMode.DRY_RUN:
            return "--ditto-prune-dry-run"
        case PruneMode.OFF:
            return None
