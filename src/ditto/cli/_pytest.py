"""Commands that run pytest with ditto's options."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from typing import NoReturn

import click
from rich.console import Console

from ._display import pass_console
from ._standalone import run_standalone


def _exit_standalone(
    flags: Sequence[str], pytest_args: Sequence[str], console: Console
) -> NoReturn:
    """Run pytest with `flags`, report on stdout and problems on stderr, then exit."""
    sys.exit(run_standalone(flags, pytest_args, console, Console(stderr=True)))


@click.command(
    name="run",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
@pass_console
def cmd_run(console: Console, pytest_args: tuple[str, ...]) -> None:
    """Run pytest, reporting any snapshot activity at the end.

    Any extra arguments are passed directly to pytest.

    \b
    Examples:
      ditto run
      ditto run tests/ci/
      ditto run tests/ci/ -k test_foo
    """
    _exit_standalone((), pytest_args, console)


@click.command(
    name="update",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
@pass_console
def cmd_update(console: Console, pytest_args: tuple[str, ...]) -> None:
    """Re-run pytest with --ditto-update to regenerate snapshots.

    Any extra arguments are passed directly to pytest.

    \b
    Examples:
      ditto update
      ditto update tests/ci/
      ditto update tests/ci/ -k test_foo
    """
    _exit_standalone(("--ditto-update",), pytest_args, console)


@click.command(
    name="prune",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.option(
    "--check",
    is_flag=True,
    default=False,
    help="Dry run: report what would be pruned, without deleting.",
)
@click.option(
    "--shared",
    is_flag=True,
    default=False,
    help=(
        "Also delete from targets other checkouts, branches or projects may "
        "share (any target but a file:// path inside the project, after "
        "following symlinks). Only safe when each has its own target path."
    ),
)
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
@pass_console
def cmd_prune(
    console: Console, check: bool, shared: bool, pytest_args: tuple[str, ...]
) -> None:
    """Re-run pytest to delete snapshots not in ditto.lock.

    With --check, report what would be pruned without deleting anything. A
    target outside the project (a remote URI, or a file:// path outside it) is
    only pruned with --shared. Any extra arguments are passed directly to
    pytest.

    \b
    Examples:
      ditto prune
      ditto prune --check
      ditto prune --shared
      ditto prune tests/ci/
    """
    flags = ["--ditto-prune-dry-run" if check else "--ditto-prune"]
    if shared:
        flags.append("--ditto-prune-shared")
    _exit_standalone(flags, pytest_args, console)


@click.command(
    name="lock",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
@pass_console
def cmd_lock(console: Console, pytest_args: tuple[str, ...]) -> None:
    """Rebuild ditto.lock from current snapshots (full run; values unchanged).

    Must run the whole suite: passing positional path/nodeid args narrows the run
    and is refused, because a narrowed rebuild can truncate entries for files it
    did not collect. Configure the suite's scope via `testpaths` in pyproject/ini
    instead.

    \b
    Examples:
      ditto lock
    """
    _exit_standalone(("--ditto-lock",), pytest_args, console)


@click.command(
    name="verify",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def cmd_verify(pytest_args):
    """Fail if the backend has drifted from ditto.lock (read-only).

    \b
    Examples:
      ditto verify
      ditto verify tests/ci/
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--ditto-verify", *pytest_args],
        check=False,
    )
    sys.exit(result.returncode)
