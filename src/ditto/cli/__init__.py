"""Snapshot management CLI. The console entry point is ``ditto.cli:cli``."""

from __future__ import annotations

import click

from ._inventory import cmd_list, cmd_status, cmd_lint, cmd_stats
from ._maintenance import cmd_clean, cmd_recorders, cmd_doctor
from ._pytest import cmd_run, cmd_update, cmd_prune, cmd_lock, cmd_verify
from ._data import RecorderInfo, _ext_map, _parse_snapshot_name, _human_size
from ._display import _RECORDER_PALETTE, _build_colour_map, render_stats
from ._diagnostics import (
    _backend_checks,
    _doctor_checks,
    _recorder_checks,
    _find_lint_issues,
)
from ._summary import (
    RecorderStats,
    SizeSummary,
    SnapshotStats,
    _format_size_summary,
    gather_stats,
)


@click.group()
@click.version_option(package_name="pytest-ditto", message="%(package)s %(version)s")
def cli():
    """pytest-ditto snapshot management."""


for command in (
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
    cli.add_command(command)
