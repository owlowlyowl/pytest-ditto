"""Commands that run pytest with ditto's options."""

from __future__ import annotations

import subprocess
import sys

import click

from ._help import examples


@click.command(
    name="run",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    epilog=examples(
        "ditto run", "ditto run tests/ci/", "ditto run tests/ci/ -k test_foo"
    ),
)
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def cmd_run(pytest_args):
    """Run pytest, passing every argument through to it.

    This is the same as running pytest directly: ditto's pytest plugin prints
    the snapshot report at the end of every run.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *pytest_args],
        check=False,
    )
    sys.exit(result.returncode)


@click.command(
    name="update",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    epilog=examples(
        "ditto update", "ditto update tests/ci/", "ditto update tests/ci/ -k test_foo"
    ),
)
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def cmd_update(pytest_args):
    """Re-run pytest with --ditto-update to re-record snapshots.

    Every snapshot the run reaches is overwritten with the current value. A
    full, passing run also rebuilds ditto.lock. Any extra arguments are passed
    directly to pytest.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--ditto-update", *pytest_args],
        check=False,
    )
    sys.exit(result.returncode)


@click.command(
    name="prune",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    epilog=examples(
        "ditto prune",
        "ditto prune --check",
        "ditto prune --shared",
        "ditto prune tests/ci/",
    ),
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
def cmd_prune(check, shared, pytest_args):
    """Re-run pytest to delete snapshots not in ditto.lock.

    With --check, report what would be pruned without deleting anything. A
    target outside the project (a remote URI, or a file:// path outside it) is
    only pruned with --shared; --check lists its orphans apart, as shared. Any
    extra arguments are passed directly to pytest.
    """
    flags = ["--ditto-prune-dry-run" if check else "--ditto-prune"]
    if shared:
        flags.append("--ditto-prune-shared")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *flags, *pytest_args],
        check=False,
    )
    sys.exit(result.returncode)


@click.command(
    name="lock",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    epilog=examples("ditto lock"),
)
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def cmd_lock(pytest_args):
    """Rebuild ditto.lock from a full run of the suite.

    Runs the whole suite, creating missing snapshots but leaving existing
    values unchanged, then rewrites the lock from the snapshots the tests used.
    A run that is filtered (-k, -m, --lf, --ff), narrowed to paths or node ids,
    or failing is refused and leaves the lock unchanged. Set the suite's scope
    with testpaths in your pytest configuration instead.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--ditto-lock", *pytest_args],
        check=False,
    )
    sys.exit(result.returncode)


@click.command(
    name="verify",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    epilog=examples("ditto verify", "ditto verify tests/ci/"),
)
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def cmd_verify(pytest_args):
    """Fail if stored snapshots have drifted from ditto.lock (read-only).

    Runs pytest with --ditto-verify. In each snapshot target the run uses, it
    reports snapshots the lock records but storage lacks (missing), stored
    snapshots the lock doesn't record (orphan) and snapshots the run produced
    that the lock doesn't record (unsynced). It doesn't compare snapshot values
    (your tests do that), and it writes nothing.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--ditto-verify", *pytest_args],
        check=False,
    )
    sys.exit(result.returncode)
