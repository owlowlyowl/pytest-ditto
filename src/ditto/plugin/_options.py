from __future__ import annotations

from typing import cast

import pytest

from ditto.exceptions import DittoAmbiguousTargetError


__all__ = (
    "StorageOptions",
    "StorageOptionsByScheme",
    "add_options",
    "validate_options",
    "validate_target_config",
    "get_optional_fixturevalue",
    "get_storage_options",
    "is_xdist_worker",
    "xdist_is_distributing",
)


StorageOptions = dict[str, object]
StorageOptionsByScheme = dict[str, StorageOptions]


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


def validate_options(config: pytest.Config) -> None:
    """Raise `pytest.UsageError` for conflicting ditto options."""
    if config.getoption("--ditto-verify", default=False) and (
        config.getoption("--ditto-update", default=False)
        or config.getoption("--ditto-lock", default=False)
        or config.getoption("--ditto-prune", default=False)
        or config.getoption("--ditto-prune-dry-run", default=False)
    ):
        raise pytest.UsageError(
            "--ditto-verify is read-only and cannot be combined with "
            "--ditto-update, --ditto-lock, --ditto-prune, or "
            "--ditto-prune-dry-run."
        )
    if config.getoption("--ditto-prune", default=False) and config.getoption(
        "--ditto-prune-dry-run", default=False
    ):
        raise pytest.UsageError(
            "--ditto-prune and --ditto-prune-dry-run cannot be combined."
        )
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
    empty and any lock write would be wrong (see #83). `numprocesses` is set by
    `-n auto`/`-n N` and is falsy (`None`/`0`) for single-process runs.
    """
    return bool(getattr(config.option, "numprocesses", None))
