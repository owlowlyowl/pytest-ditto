"""Commands that report on the snapshots under a path."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from .._cli_introspect import IntrospectError
from .._inventory import (
    InventoryError,
    build_inventory,
    lock_identities,
    lock_present,
)
from .._manifest import Manifest, ManifestEntry
from .._theme import MUTED, PRUNED
from ._data import _ext_map, _load_recorder_infos
from ._diagnostics import _find_lint_issues
from ._display import (
    _render_lint_issues,
    _render_snapshots,
    _render_stats_table,
    render_stats,
)
from ._summary import gather_stats

console = Console()

_live_option = click.option(
    "--live",
    is_flag=True,
    default=False,
    help="Read live backends via a pytest pass (needs credentials) instead of "
    "the credential-free filesystem + ditto.lock inventory.",
)


def _inventory_or_exit(path: Path, *, live: bool) -> Manifest:
    """Build the inventory for PATH, or print the error and exit(1)."""
    try:
        return build_inventory(path, live=live)
    except IntrospectError as exc:
        console.print(f"[bold {PRUNED}]Introspection failed:[/bold {PRUNED}] {exc}")
        sys.exit(1)
    except InventoryError as exc:
        console.print(f"[bold {PRUNED}]Inventory failed:[/bold {PRUNED}] {exc}")
        sys.exit(1)


def _print_inventory_notes(
    path: Path, entries: list[ManifestEntry], *, live: bool
) -> None:
    """Print muted hints about unknown remote sizes and a missing lock file."""
    if live:
        return
    unknown = sum(1 for entry in entries if entry.size_bytes is None)
    if unknown:
        plural = "s" if unknown != 1 else ""
        console.print(
            f"[{MUTED}]remote: {unknown} snapshot{plural}, "
            f"size unknown (use --live).[/{MUTED}]"
        )
    if not lock_present(path):
        console.print(
            f"[{MUTED}]no ditto.lock found — remote snapshots are not shown; "
            f"use --live.[/{MUTED}]"
        )


def _entries(manifest: Manifest) -> list[ManifestEntry]:
    """Flatten all entries across the manifest's backends."""
    return [e for b in manifest for e in b.entries]


@click.command(name="list")
@_live_option
@click.argument(
    "path", default=".", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
def cmd_list(path: Path, live: bool):
    """List all snapshot files under PATH (default: current directory).

    By default reads local snapshots from disk and remote snapshots from
    ditto.lock (credential-free); pass --live to read live backends.

    \b
    Examples:
      ditto list
      ditto list tests/ci/
    """
    manifest = _inventory_or_exit(path, live=live)
    entries = _entries(manifest)
    if not entries:
        console.print(f"[{MUTED}]No snapshot files found.[/{MUTED}]")
        _print_inventory_notes(path, entries, live=live)
        sys.exit(1)

    infos = _load_recorder_infos()
    _render_snapshots(manifest, lock_identities(path), infos, console)
    _print_inventory_notes(path, entries, live=live)


@click.command(name="status")
@_live_option
@click.argument(
    "path", default=".", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
def cmd_status(path: Path, live: bool):
    """Show aggregate statistics for snapshots under PATH.

    By default aggregates local snapshots from disk and remote snapshots from
    ditto.lock (credential-free); pass --live to read live backends.

    \b
    Examples:
      ditto status
      ditto status tests/ci/
    """
    manifest = _inventory_or_exit(path, live=live)
    entries = _entries(manifest)
    if not entries:
        console.print(f"[{MUTED}]No snapshot files found.[/{MUTED}]")
        _print_inventory_notes(path, entries, live=live)
        sys.exit(1)

    render_stats(gather_stats(entries, _ext_map(_load_recorder_infos())), console)
    _print_inventory_notes(path, entries, live=live)


@click.command(name="lint")
@_live_option
@click.argument(
    "path", default=".", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
def cmd_lint(path: Path, live: bool):
    """Check snapshot files for naming issues, unknown formats, and empty files.

    By default lints local snapshots from disk and remote snapshots from
    ditto.lock (credential-free); pass --live to read live backends.

    \b
    Examples:
      ditto lint
      ditto lint tests/ci/
    """
    manifest = _inventory_or_exit(path, live=live)
    entries = _entries(manifest)
    issues = _find_lint_issues(entries, _ext_map(_load_recorder_infos()))
    if issues:
        _render_lint_issues(issues, console)
    else:
        console.print(f"[{MUTED}]All snapshots are valid.[/{MUTED}]")
    _print_inventory_notes(path, entries, live=live)
    if issues:
        sys.exit(1)


@click.command(name="stats")
@_live_option
@click.argument(
    "path", default=".", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
def cmd_stats(path: Path, live: bool):
    """Show per-directory snapshot usage breakdown.

    By default breaks down local snapshots from disk and remote snapshots from
    ditto.lock (credential-free); pass --live to read live backends.

    \b
    Examples:
      ditto stats
      ditto stats tests/ci/
    """
    manifest = _inventory_or_exit(path, live=live)
    if not manifest:
        console.print(f"[{MUTED}]No snapshot files found.[/{MUTED}]")
        _print_inventory_notes(path, [], live=live)
        sys.exit(1)
    em = _ext_map(_load_recorder_infos())
    dir_stats = [(b.location, gather_stats(b.entries, em)) for b in manifest]
    _render_stats_table(dir_stats, console)
    _print_inventory_notes(path, _entries(manifest), live=live)
