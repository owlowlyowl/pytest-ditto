"""Presentation regressions: identity, wrapping, literal data, and empty values."""

from io import StringIO
import re

import pytest
from rich.console import Console

from ditto._lockfile import LockEntry
from ditto._manifest import BackendManifest, ManifestEntry
from ditto.cli._data import RecorderInfo
from ditto.cli._diagnostics import CheckResult, LintIssue
from ditto.cli._display import (
    _build_colour_map,
    _render_doctor,
    _render_lint_issues,
    _render_recorders,
    _render_snapshots,
    _render_stats_table,
    render_stats,
)
from ditto.cli._summary import gather_stats


def render(renderer, *args, width=80, **kwargs):
    stream = StringIO()
    console = Console(file=stream, width=width, color_system=None)
    renderer(*args, console, **kwargs)
    return stream.getvalue()


def unframe(output):
    """Rejoin folded cells without relying on decorative frame characters."""
    return re.sub(r"[\s│]", "", output)


@pytest.mark.parametrize("width", [40, 60, 80, 120])
def test_tree_keeps_full_identity_and_metadata_at_small_widths(width):
    location = "memory://snapshots"
    nodeid = "tests/integration/test_api.py::TestAPI::test_response[param::a/b.json]"
    key = "[/]"
    stored = (
        "tests.integration.test_api.TestAPI.test_response@key~0123456789abcdef.json"
    )
    entry = ManifestEntry(stored, 1536, None)
    identities = {(location, stored): LockEntry(nodeid, key, "json")}

    output = render(
        _render_snapshots,
        [BackendManifest(location, [entry])],
        {},
        identities,
        width=width,
    )

    assert all(len(line) <= width for line in output.splitlines())
    assert "…" not in output
    assert "tests/integration/test_api.py" in unframe(output)
    first_column = "".join(
        line.split("│")[1].strip().removeprefix("└─ ")
        for line in output.splitlines()
        if line.startswith("│")
    )
    assert nodeid.split("::", 1)[1] in first_column
    for fragment in ("[/]", "1.5 KB"):
        assert fragment in output
    assert "1 snapshot · 1 target" in output


def test_tree_groups_shared_file_once_but_separates_targets():
    stored = "test_api.test_a@k~0123456789abcdef.json"
    locations = ["memory://one", "memory://two"]
    manifest = [
        BackendManifest(location, [ManifestEntry(stored, None, None)])
        for location in locations
    ]
    identities = {
        (location, stored): LockEntry("test_api.py::test_a", "[red]", "json")
        for location in locations
    }
    output = render(_render_snapshots, manifest, {}, identities)

    assert output.count("test_api.py") == 2
    assert output.count("test_a") == 4  # file heading and leaf in each target
    assert output.count("[red]") == 2
    assert all(location in output for location in locations)
    assert "2 snapshots · 2 targets" in output


def test_file_heading_is_not_repeated_for_each_snapshot():
    location = "memory://snapshots"
    entries = [
        ManifestEntry(f"test_api.test_a@{key}~0123456789abcdef.json", 1, None)
        for key in ("a", "b")
    ]
    identities = {
        (location, entry.storage_key): LockEntry(
            "tests/test_api.py::test_a", key, "json"
        )
        for key, entry in zip(("a", "b"), entries)
    }
    output = render(
        _render_snapshots, [BackendManifest(location, entries)], {}, identities
    )
    assert output.count("tests/test_api.py") == 1
    assert "├─ test_a" in output
    assert "└─ test_a" in output


def test_flat_keeps_full_node_ids():
    location = "memory://one"
    stored = "test_a@k~0123456789abcdef.json"
    nodeid = "tests/test_a.py::test_a[::]"
    output = render(
        _render_snapshots,
        [BackendManifest(location, [ManifestEntry(stored, 1, None)])],
        {},
        {(location, stored): LockEntry(nodeid, "key", "json")},
        flat=True,
        width=120,
    )
    assert nodeid in output
    assert "├─ " not in output and "└─ " not in output


def test_unlocked_labels_are_not_guessed_into_file_paths():
    stored = "ambiguous.module.test[with.dots]@k~0123456789abcdef.json"
    output = render(
        _render_snapshots,
        [BackendManifest("memory://one", [ManifestEntry(stored, 1, None)])],
        {},
        {},
        width=120,
    )
    assert "ambiguous.module.test[with.dots]" in output
    assert "not in lock" in output


@pytest.mark.parametrize(
    "renderer,args",
    [
        (_render_doctor, ([CheckResult("[bold]check[/]", False, "[/]error[red]")],)),
        (
            _render_lint_issues,
            ([LintIssue("[/]file[red]", "[/]error[red]", "memory://[red]")],),
        ),
        (_render_recorders, ([RecorderInfo("[red]", "[/]", "[bold]package[/]")],)),
        (_render_stats_table, ([("memory://[red]", gather_stats([], {}))],)),
    ],
)
def test_external_text_is_never_interpreted_as_markup(renderer, args):
    output = render(renderer, *args, width=120)
    assert "[red]" in output


def test_empty_summary_renders_without_max_of_empty_sequence():
    assert "0 snapshots" in render(render_stats, gather_stats([], {}))


def test_duplicate_names_do_not_change_recorder_colours():
    assert _build_colour_map(["json", "json", "yaml"]) == _build_colour_map([
        "json",
        "yaml",
    ])
