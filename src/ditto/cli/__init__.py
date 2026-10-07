"""
ditto CLI — snapshot management for pytest-ditto.

Subcommands
-----------
run         Run pytest, reporting any snapshot activity at the end.
update      Re-run pytest with --ditto-update to regenerate snapshots.
prune       Re-run pytest with --ditto-prune to remove stale snapshots.
lock        Rebuild ditto.lock from current snapshots.
verify      Fail if the backend has drifted from ditto.lock (read-only).
list        List all snapshot files under a path.
clean       Delete all .ditto/ directories under a path.
status      Show aggregate statistics for snapshots under a path.
recorders   List all registered recorder plugins.
doctor      Run health checks on the ditto installation and plugins.
lint        Check snapshot files for naming, format, and integrity issues.
stats       Show per-directory snapshot usage breakdown.
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
