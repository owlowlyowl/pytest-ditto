"""Regenerate the CLI documentation's SVG examples without accessing backends.

Run from the repository root with an installed pytest-ditto development env:
    python scripts/render_cli_examples.py
"""

from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

from rich.console import Console
from rich.terminal_theme import TerminalTheme

from ditto._inventory import location_key
from ditto._lockfile import LockEntry, storage_key
from ditto._manifest import BackendManifest, ManifestEntry
from ditto.cli._data import RecorderInfo
from ditto.cli._display import _render_recorders, _render_snapshots, render_stats
from ditto.cli._summary import gather_stats


OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "src" / "img"
THEME = TerminalTheme(
    (30, 30, 46),
    (205, 214, 244),
    [
        (69, 71, 90),
        (243, 139, 168),
        (166, 227, 161),
        (249, 226, 175),
        (137, 180, 250),
        (203, 166, 247),
        (148, 226, 213),
        (205, 214, 244),
    ],
)


def main() -> None:
    date = datetime(2026, 9, 30, 12, tzinfo=timezone.utc).timestamp()
    location = "tests/integration/.ditto"
    entries = []
    identities = {}
    examples = [
        (
            "tests/integration/test_checkout.py::TestCheckout::test_receipt[express]",
            "receipt",
            "json",
            1536,
        ),
        (
            "tests/integration/test_checkout.py::TestCheckout::test_receipt[express]",
            "totals",
            "json",
            248,
        ),
        (
            "tests/integration/test_inventory.py::test_available_items",
            "items",
            "yaml",
            384,
        ),
    ]
    for nodeid, key, recorder, size in examples:
        locked = LockEntry(nodeid, key, recorder)
        stored = storage_key(locked, "file")
        entries.append(ManifestEntry(stored, size, date))
        identities[(location_key(location), stored)] = locked
    manifest = [BackendManifest(location, entries)]
    infos = [
        RecorderInfo(name, f".{name}", "pytest-ditto") for name in ("json", "yaml")
    ]
    em = {info.identifier: info for info in infos}
    for name in ("list", "status", "recorders"):
        console = Console(
            file=StringIO(), width=100, record=True, color_system="truecolor"
        )
        if name == "list":
            _render_snapshots(manifest, em, identities, console)
        elif name == "status":
            render_stats(gather_stats(entries, em), console)
        else:
            _render_recorders(infos, console)
        console.save_svg(
            str(OUTPUT / f"ditto-{name}.svg"), title=f"ditto {name}", theme=THEME
        )


if __name__ == "__main__":
    main()
