"""Commands that report on the snapshots under a path."""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

import click
from rich.console import Console
from rich.text import Text

from .._cli_introspect import IntrospectError
from .._inventory import (
    InventoryError,
    build_inventory,
    location_key,
    lock_identities,
    lock_present,
)
from .._lockfile import LockEntry
from .._manifest import BackendManifest, Manifest, ManifestEntry
from .._theme import MUTED, PRUNED
from ._data import _ext_map, _load_recorder_infos, nodeid_selected
from ._diagnostics import _find_lint_issues
from ._display import (
    _render_lint_issues,
    _render_snapshots,
    _render_stats_table,
    _render_unreadable_backends,
    pass_console,
    render_stats,
)
from ._help import examples
from ._summary import gather_stats, oldest_and_newest


_live_option = click.option(
    "--live",
    is_flag=True,
    default=False,
    help="Read live backends via a pytest pass (needs credentials) instead of "
    "the credential-free filesystem + ditto.lock inventory.",
)


def _inventory_or_exit(path: Path, *, live: bool, console: Console) -> Manifest:
    """Build the inventory for PATH, or print the error and exit(1)."""
    try:
        return build_inventory(path, live=live)
    except IntrospectError as exc:
        console.print(
            Text.assemble(("Introspection failed: ", f"bold {PRUNED}"), str(exc))
        )
        sys.exit(1)
    except InventoryError as exc:
        console.print(Text.assemble(("Inventory failed: ", f"bold {PRUNED}"), str(exc)))
        sys.exit(1)


def _print_inventory_notes(
    path: Path, entries: list[ManifestEntry], *, live: bool, console: Console
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


def _unreadable(manifest: Manifest) -> list[BackendManifest]:
    """The backends the live pass couldn't enumerate."""
    return [b for b in manifest if b.error is not None]


def _exit_if_incomplete(manifest: Manifest, console: Console) -> None:
    """Report each backend that couldn't be read, if any, and exit(1)."""
    unreadable = _unreadable(manifest)
    if unreadable:
        _render_unreadable_backends(unreadable, console)
        sys.exit(1)


def _select_tests(
    manifest: Manifest,
    identities: Mapping[tuple[str, str], LockEntry] | None,
    selectors: Sequence[str],
) -> tuple[Manifest, int]:
    """Keep the entries whose test the selectors select; count unlocked ones.

    Only the lock knows a snapshot's node id, so an entry it doesn't record
    can't be matched. It's left out and counted, so the caller can say so.
    """
    identities = identities or {}
    kept: Manifest = []
    unlocked = 0
    for backend in manifest:
        entries = []
        for entry in backend.entries:
            identity = identities.get((
                location_key(backend.location),
                entry.storage_key,
            ))
            if identity is None:
                unlocked += 1
            elif nodeid_selected(identity.nodeid, selectors):
                entries.append(entry)
        kept.append(replace(backend, entries=entries))
    return kept, unlocked


def _print_unlocked_note(unlocked: int, console: Console) -> None:
    if not unlocked:
        return
    plural = "s" if unlocked != 1 else ""
    console.print(
        Text(
            f"Left out {unlocked} snapshot{plural} that ditto.lock doesn't record: "
            "--test matches the lock's node ids.",
            style=MUTED,
        )
    )


@click.command(
    name="list",
    epilog=examples(
        "ditto list",
        "ditto list tests/ci/",
        "ditto list --test tests/ci/test_api.py::test_totals",
    ),
)
@_live_option
@click.option(
    "--test",
    "tests",
    multiple=True,
    metavar="NODEID",
    help="Only snapshots of this test: an exact node id, or a prefix ending at "
    "`/`, `::` or `[`. Repeatable.",
)
@click.argument(
    "path", default=".", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
@pass_console
def cmd_list(console: Console, path: Path, live: bool, tests: tuple[str, ...]):
    """List all snapshot files under PATH (default: current directory).

    By default reads local snapshots from disk and remote snapshots from
    ditto.lock (credential-free); pass --live to read live backends.

    --test keeps the snapshots of the tests it names, matched by the node id
    ditto.lock records for them. Node ids are relative to the rootdir.
    """
    manifest = _inventory_or_exit(path, live=live, console=console)
    identities = lock_identities(path)
    unlocked = 0
    if tests:
        manifest, unlocked = _select_tests(manifest, identities, tests)
    entries = _entries(manifest)
    if not entries:
        _exit_if_incomplete(manifest, console)
        console.print(f"[{MUTED}]No snapshot files found.[/{MUTED}]")
        _print_unlocked_note(unlocked, console)
        _print_inventory_notes(path, entries, live=live, console=console)
        sys.exit(1)

    infos = _load_recorder_infos()
    _render_snapshots(manifest, identities, infos, console)
    _print_unlocked_note(unlocked, console)
    _print_inventory_notes(path, entries, live=live, console=console)
    _exit_if_incomplete(manifest, console)


@click.command(name="status", epilog=examples("ditto status", "ditto status tests/ci/"))
@_live_option
@click.argument(
    "path", default=".", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
@pass_console
def cmd_status(console: Console, path: Path, live: bool):
    """Show aggregate statistics for snapshots under PATH.

    By default aggregates local snapshots from disk and remote snapshots from
    ditto.lock (credential-free); pass --live to read live backends.
    """
    manifest = _inventory_or_exit(path, live=live, console=console)
    entries = _entries(manifest)
    if not entries:
        _exit_if_incomplete(manifest, console)
        console.print(f"[{MUTED}]No snapshot files found.[/{MUTED}]")
        _print_inventory_notes(path, entries, live=live, console=console)
        sys.exit(1)

    em = _ext_map(_load_recorder_infos())
    render_stats(
        gather_stats(entries, em),
        oldest_and_newest(manifest),
        lock_identities(path),
        em,
        console,
    )
    _print_inventory_notes(path, entries, live=live, console=console)
    _exit_if_incomplete(manifest, console)


@click.command(name="lint", epilog=examples("ditto lint", "ditto lint tests/ci/"))
@_live_option
@click.argument(
    "path", default=".", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
@pass_console
def cmd_lint(console: Console, path: Path, live: bool):
    """Check snapshot files for naming issues, unknown formats, and empty files.

    By default lints local snapshots from disk and remote snapshots from
    ditto.lock (credential-free); pass --live to read live backends.
    """
    manifest = _inventory_or_exit(path, live=live, console=console)
    entries = _entries(manifest)
    issues = _find_lint_issues(entries, _ext_map(_load_recorder_infos()))
    if issues:
        _render_lint_issues(issues, console)
    elif not _unreadable(manifest):
        console.print(f"[{MUTED}]All snapshots are valid.[/{MUTED}]")
    _print_inventory_notes(path, entries, live=live, console=console)
    _exit_if_incomplete(manifest, console)
    if issues:
        sys.exit(1)


@click.command(name="stats", epilog=examples("ditto stats", "ditto stats tests/ci/"))
@_live_option
@click.argument(
    "path", default=".", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
@pass_console
def cmd_stats(console: Console, path: Path, live: bool):
    """Show the snapshot count, size and recorders of each target under PATH.

    By default reads local snapshots from disk and remote snapshots from
    ditto.lock (credential-free); pass --live to read live backends.
    """
    manifest = _inventory_or_exit(path, live=live, console=console)
    if not manifest:
        console.print(f"[{MUTED}]No snapshot files found.[/{MUTED}]")
        _print_inventory_notes(path, [], live=live, console=console)
        sys.exit(1)
    em = _ext_map(_load_recorder_infos())
    dir_stats = [
        (b.location, gather_stats(b.entries, em)) for b in manifest if b.error is None
    ]
    if dir_stats:
        _render_stats_table(dir_stats, console)
    _print_inventory_notes(path, _entries(manifest), live=live, console=console)
    _exit_if_incomplete(manifest, console)
