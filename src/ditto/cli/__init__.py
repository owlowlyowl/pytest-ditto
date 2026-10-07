"""
ditto CLI — snapshot management for pytest-ditto.

Subcommands
-----------
run         Run pytest, passing every argument through to it.
update      Re-run pytest with --ditto-update to re-record snapshots.
prune       Re-run pytest to delete snapshots not in ditto.lock.
lock        Rebuild ditto.lock from a full run of the suite.
verify      Fail if stored snapshots have drifted from ditto.lock (read-only).
list        List all snapshot files under a path.
clean       Delete all .ditto/ directories under a path.
status      Show aggregate statistics for snapshots under a path.
recorders   List the installed recorders, their marks and where they come from.
doctor      Check that ditto and its plugins are installed correctly.
lint        Check snapshot files for naming issues, unknown formats, and empty files.
stats       Show the snapshot count, size and recorders of each target.
"""

from __future__ import annotations

import click

from ._inventory import cmd_lint, cmd_list, cmd_stats, cmd_status
from ._maintenance import cmd_clean, cmd_doctor, cmd_recorders
from ._pytest import cmd_lock, cmd_prune, cmd_run, cmd_update, cmd_verify


@click.group()
@click.version_option(package_name="pytest-ditto", message="%(package)s %(version)s")
def cli():
    """pytest-ditto snapshot management."""


for _command in (
    cmd_run,
    cmd_update,
    cmd_prune,
    cmd_lock,
    cmd_verify,
    cmd_list,
    cmd_clean,
    cmd_status,
    cmd_recorders,
    cmd_doctor,
    cmd_lint,
    cmd_stats,
):
    cli.add_command(_command)
