"""The CLI's output at a normal terminal width: identity, grouping, no truncation.

Covers the redesign in #182: one way to name a snapshot, relative paths,
wrapping in the middle instead of truncating, and every view built as a Rich
table that fits the width it is given.
"""

import json
import re
from io import StringIO

import pytest
from click.testing import CliRunner
from rich.console import Console

from ditto._inventory import location_key
from ditto._lockfile import LockEntry
from ditto._manifest import BackendManifest, LocatedEntry, ManifestEntry
from ditto._report import PrunedSnapshot, ReportedSnapshot, render_session_report
from ditto.cli._data import RecorderInfo
from ditto.cli import cli
from ditto.cli._display import (
    _render_recorders,
    _render_snapshots,
    _render_stats_table,
    render_stats,
)
from ditto.cli._summary import gather_stats


INFOS = [
    RecorderInfo("json", ".json", "pytest-ditto"),
    RecorderInfo("pandas.parquet", ".pandas.parquet", "pytest-ditto-pandas"),
]

WIDTHS = [60, 80, 120]


def render(renderer, *args, width: int = 80, **kwargs) -> str:
    """Render at `width` columns with no colour, and return the text."""
    stream = StringIO()
    renderer(*args, Console(file=stream, width=width, color_system=None), **kwargs)
    return stream.getvalue()


def manifest_of(*entries: tuple[str, str], location: str = "tests/.ditto"):
    """A manifest of `(storage_key, nodeid)` pairs, with each node id's key."""
    return [
        BackendManifest(
            location,
            [ManifestEntry(stored, 13, 1_759_000_000.0) for stored, _ in entries],
        )
    ]


def identities_of(*entries: tuple[str, str], location: str = "tests/.ditto"):
    """The lock identities matching `manifest_of`, keyed by target and name."""
    return {
        (location_key(location), stored): LockEntry(nodeid, "value", "json")
        for stored, nodeid in entries
    }


# ── every view fits the width, and nothing is truncated ──────────────────────


@pytest.mark.parametrize("width", [40, 59, 60, 79, 80, 120])
def test_list_never_exceeds_the_width(width: int) -> None:
    """No line is wider than the console, at any width the CLI supports."""
    entries = (
        (
            "tests.test_a.test_numbers[1]@value~e51845259fe080be.json",
            "tests/integration/test_api.py::TestAPI::test_response[param::a/b.json]",
        ),
        (
            "tests.test_a.test_frame@df~c092c1ce8977e48f.pandas.parquet",
            "tests/integration/test_api.py::test_frame",
        ),
    )
    output = render(
        _render_snapshots,
        manifest_of(*entries),
        identities_of(*entries),
        INFOS,
        width=width,
    )

    assert all(len(line) <= width for line in output.splitlines())


@pytest.mark.parametrize("width", [80, 120])
def test_recorders_never_wrap_a_plugin_onto_its_own_line(width: int) -> None:
    """A row stays on one line even with a plugin name as long as the widest."""
    infos = [
        RecorderInfo("pandas.parquet", ".pandas.parquet", "pytest-ditto-pandas"),
        RecorderInfo("pyarrow.feather", ".pyarrow.feather", "pytest-ditto-pyarrow"),
    ]

    output = render(_render_recorders, infos, width=width)

    assert all(len(line) <= width for line in output.splitlines())
    assert output.count("pytest-ditto-pyarrow") == 1


@pytest.mark.parametrize("width", WIDTHS)
def test_stats_never_exceeds_the_width(width: int) -> None:
    """A long remote location wraps rather than being cut off at the end."""
    location = "s3://a-very-long-bucket-name/another-long-segment/deeper-still"

    output = render(
        _render_stats_table,
        [
            (
                location,
                gather_stats(
                    [
                        LocatedEntry(
                            location, ManifestEntry("a@b~0" * 16 + ".json", 13, None)
                        )
                    ],
                    {},
                ),
            )
        ],
        width=width,
    )

    assert all(len(line) <= width for line in output.splitlines())
    assert "…" not in output


# ── one way to name a snapshot (#182, #190) ───────────────────────────────────


@pytest.mark.parametrize("width", [40, 59, 60, 79, 80, 120])
def test_list_keeps_the_parametrize_id_and_key_intact(width: int) -> None:
    """A node id that would be truncated from the end is shown whole."""
    nodeid = "tests/integration/test_api.py::test_response[param::a/b.json]"
    stored = "tests.test_a.test_response@value~e51845259fe080be.json"

    output = render(
        _render_snapshots,
        manifest_of((stored, nodeid)),
        identities_of((stored, nodeid)),
        INFOS,
        width=width,
    )
    first_column = re.sub(
        r"\s+",
        "",
        "".join(
            line.split("│")[1] for line in output.splitlines() if line.startswith("│")
        ),
    )

    assert "test_response[param::a/b.json]" in first_column
    assert "tests/integration/test_api.py" in first_column
    assert "value" in output


def test_list_groups_a_file_heading_once_for_all_its_snapshots() -> None:
    """Two snapshots in one file share the file heading rather than repeat it."""
    entries = (
        ("tests.test_a.test_x@a~0123456789abcdef.json", "tests/test_a.py::test_x"),
        ("tests.test_a.test_x@b~1111111111111111.json", "tests/test_a.py::test_x"),
    )

    output = render(
        _render_snapshots, manifest_of(*entries), identities_of(*entries), INFOS
    )

    assert output.count("tests/test_a.py") == 1
    assert "├─ test_x" in output
    assert "└─ test_x" in output


def test_list_separates_the_same_key_under_two_targets() -> None:
    """The same storage name in two targets reads as two snapshots."""
    stored = "test_api.test_a@k~0123456789abcdef.json"
    manifest = [
        BackendManifest(location, [ManifestEntry(stored, None, None)])
        for location in ("memory://one", "memory://two")
    ]
    identities = {
        (location_key(location), stored): LockEntry(
            "test_api.py::test_a", "value", "json"
        )
        for location in ("memory://one", "memory://two")
    }

    output = render(_render_snapshots, manifest, identities, INFOS)

    assert "memory://one" in output
    assert "memory://two" in output
    assert "2 snapshots · 2 targets" in output


@pytest.mark.parametrize("width", [40, 59, 80, 120])
def test_flat_keeps_the_whole_node_id_and_target_on_one_line(width) -> None:
    nodeid = "tests/integration/test_api.py::test_response[param::a/b.json]"
    stored = "test_a@k~0123456789abcdef.json"
    targets = ["memory://one", "memory://two"]
    manifest = [manifest_of((stored, nodeid), location=t)[0] for t in targets]
    identities = {
        identity: entry
        for target in targets
        for identity, entry in identities_of((stored, nodeid), location=target).items()
    }

    output = render(
        _render_snapshots,
        manifest,
        identities,
        INFOS,
        width=width,
        flat=True,
    )

    lines = output.splitlines()
    assert len(lines) == 2
    assert all(nodeid in line for line in lines)
    records = [json.loads(line) for line in lines]
    assert [r["target"] for r in records] == targets
    assert all(r["nodeid"] == nodeid and r["key"] == "value" for r in records)
    assert all(r["recorder"] == "json" and r["in_lock"] is True for r in records)


@pytest.mark.parametrize("width", [40, 59])
def test_narrow_list_places_identity_and_metadata_in_two_columns(width):
    stored = "test_a@k~0123456789abcdef.json"
    nodeid = "test_a.py::test_a"
    output = render(
        _render_snapshots,
        manifest_of((stored, nodeid)),
        identities_of((stored, nodeid)),
        INFOS,
        width=width,
    )
    rows = [line.split("│")[1:-1] for line in output.splitlines() if "│" in line]
    assert all(len(row) == 2 for row in rows), output
    identity_column = "".join(row[0].strip() for row in rows)
    details_column = "".join(row[1].strip() for row in rows)
    assert "test_a" in identity_column
    assert "Key: value" in identity_column
    assert "json" in identity_column
    assert "13 B" in details_column
    assert re.search(r"\d{4}-\d{2}-\d{2}", details_column)


def test_flat_escapes_control_characters_and_preserves_literal_markup():
    stored = "test_a@k~0123456789abcdef.json"
    nodeid = 'test_a.py::test_a[red]\n["quoted"]'
    identities = identities_of((stored, nodeid))
    identities[(location_key("tests/.ditto"), stored)] = LockEntry(
        nodeid, "key\twith\nlines\\and[red]", "json"
    )
    output = render(
        _render_snapshots,
        manifest_of((stored, nodeid)),
        identities,
        INFOS,
        width=40,
        flat=True,
    )
    assert len(output.splitlines()) == 1
    record = json.loads(output)
    assert record["nodeid"] == nodeid
    assert record["key"] == "key\twith\nlines\\and[red]"


@pytest.mark.parametrize("identities, in_lock", [(None, None), ({}, False)])
def test_flat_does_not_guess_unknown_identities(identities, in_lock):
    stored = "lossy.test_label@key_label~0123456789abcdef.json"
    output = render(
        _render_snapshots,
        manifest_of((stored, "unused")),
        identities,
        INFOS,
        flat=True,
    )
    record = json.loads(output)
    assert record["nodeid"] is None and record["key"] is None
    assert record["storage_key"] == stored
    assert record["recorder"] == "json"
    assert record["in_lock"] is in_lock


def test_flat_redirected_stdout_contains_only_json(tmp_path):
    directory = tmp_path / ".ditto"
    directory.mkdir()
    (directory / "test_a@k~0123456789abcdef.json").write_text("1")
    result = CliRunner().invoke(cli, ["list", "--flat", str(tmp_path)])
    assert result.exit_code == 0, result.output
    records = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(records) == 1
    assert records[0]["target"] == str(directory)
    assert "no ditto.lock" in result.stderr


def test_flat_empty_inventory_keeps_diagnostics_off_stdout(tmp_path):
    result = CliRunner().invoke(cli, ["list", "--flat", str(tmp_path)])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "No snapshot files" in result.stderr


def test_flat_incomplete_inventory_keeps_diagnostics_off_stdout(tmp_path, monkeypatch):
    from ditto.cli import _inventory

    monkeypatch.setattr(
        _inventory,
        "build_inventory",
        lambda *args, **kwargs: [
            BackendManifest("memory://good", [ManifestEntry("a.json", None, None)]),
            BackendManifest("memory://bad", [], error="denied"),
        ],
    )
    result = CliRunner().invoke(cli, ["list", "--flat", "--live", str(tmp_path)])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["target"] == "memory://good"
    assert "Inventory incomplete" in result.stderr


def test_list_marks_a_name_the_lock_does_not_record() -> None:
    """An orphan has no lock entry, so it is named by its label and marked."""
    stored = "ambiguous.module.test[with.dots]@k~0123456789abcdef.json"

    output = render(
        _render_snapshots,
        manifest_of((stored, "unused")),
        identities_of(("other.json", "unused")),
        INFOS,
        width=120,
    )

    assert "ambiguous.module.test[with.dots]" in output
    assert "not in lock" in output


def test_list_names_a_local_target_relative_to_the_current_directory(
    monkeypatch, tmp_path
) -> None:
    """A local target is shown as a path to type, not an absolute one."""
    stored = "test_a@k~0123456789abcdef.json"
    monkeypatch.chdir(tmp_path)
    target = str(tmp_path / "tests" / ".ditto")
    manifest = BackendManifest(target, [ManifestEntry(stored, 1, None)])

    output = render(_render_snapshots, [manifest], None, INFOS, width=120)

    assert "tests/.ditto" in output
    assert str(tmp_path) not in output


def test_status_names_the_oldest_snapshot_by_its_node_id() -> None:
    """`ditto status` names oldest and newest the way `ditto list` does."""
    stored = "tests.test_a.test_x@value~e51845259fe080be.json"
    nodeid = "tests/test_a.py::test_x"
    entries = [LocatedEntry("tests/.ditto", ManifestEntry(stored, 13, 1_759_000_000.0))]

    output = render(
        render_stats,
        gather_stats(entries, {}),
        identities_of((stored, nodeid)),
        width=80,
    )

    assert f"{nodeid}  value" in output
    assert stored not in output


def test_status_extremes_distinguish_recorders_and_targets():
    nodeid = "test_a.py::test_a"
    entries = [
        LocatedEntry("memory://one", ManifestEntry("a.json", 1, 1700000000)),
        LocatedEntry("memory://two", ManifestEntry("a.yaml", 2, 1759000000)),
    ]
    identities = {
        (entry.location, entry.entry.storage_key): LockEntry(nodeid, "k", recorder)
        for entry, recorder in zip(entries, ["json", "yaml"])
    }
    output = render(render_stats, gather_stats(entries, {}), identities)
    oldest, newest = output.split("Oldest", 1)[1].split("Newest", 1)
    assert "memory://one" in oldest and f"{nodeid}  k  json" in oldest
    assert "memory://two" in newest and f"{nodeid}  k  yaml" in newest


def test_local_target_outside_cwd_is_relative(monkeypatch, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    output = render(
        _render_snapshots,
        [BackendManifest(str(tmp_path / ".ditto"), [ManifestEntry("a.json", 1, None)])],
        None,
        INFOS,
    )
    assert "../.ditto" in output.replace("\\", "/")
    assert str(tmp_path) not in output


# ── the recorders table fits (#180) ───────────────────────────────────────────


def test_recorders_drop_the_identifier_when_it_is_only_the_dotted_name() -> None:
    """The identifier column costs width without adding information."""
    infos = [RecorderInfo("json", ".json", "pytest-ditto")]

    output = render(_render_recorders, infos, width=120)

    assert "Identifier" not in output
    assert "json" in output
    assert "@ditto.json" in output


def test_recorders_keep_the_identifier_when_it_differs_from_the_name() -> None:
    """A recorder whose identifier isn't `.` + its name still shows it."""
    infos = [
        RecorderInfo("json", ".json", "pytest-ditto"),
        RecorderInfo("odd", "oddly", "pytest-ditto"),
    ]

    output = render(_render_recorders, infos, width=120)

    assert "Identifier" in output
    assert "oddly" in output


# ── the session report names a snapshot the same way (#181) ──────────────────


def test_report_names_a_created_snapshot_by_node_id_key_and_recorder() -> None:
    """A created snapshot is named as a test, a key and a recorder, not a path."""
    stream = StringIO()

    render_session_report(
        created=[
            ReportedSnapshot(
                "tests/.ditto", "tests/test_a.py::test_x[1]", "value", "json"
            ),
        ],
        updated=[],
        pruned=[],
        would_prune=[],
        console=Console(file=stream, width=80, color_system=None),
    )
    output = stream.getvalue()

    assert "tests/test_a.py::test_x[1]" in output
    assert "value" in output
    assert "json" in output
    assert "tests/test_a/test_x" not in output


def test_report_groups_snapshots_under_the_target_they_went_to() -> None:
    """Two targets' snapshots are listed under their own headings."""
    stream = StringIO()

    render_session_report(
        created=[
            ReportedSnapshot("tests/.ditto", "tests/test_a.py::test_x", "v", "json"),
            ReportedSnapshot("s3://bucket/dir", "tests/test_b.py::test_y", "v", "json"),
        ],
        updated=[],
        pruned=[],
        would_prune=[],
        console=Console(file=stream, width=80, color_system=None),
    )
    output = stream.getvalue()

    assert output.index("tests/.ditto") < output.index("tests/test_a.py::test_x")
    assert output.index("s3://bucket/dir") < output.index("tests/test_b.py::test_y")


@pytest.mark.parametrize("width", WIDTHS)
def test_report_keeps_each_snapshot_on_its_own_line(width: int) -> None:
    """A long name wraps without knocking the next snapshot out of alignment."""
    stream = StringIO()
    long_nodeid = (
        "tests/" + "deeply/" * 6 + "nested/test_module.py::test_something[param]"
    )

    render_session_report(
        created=[
            ReportedSnapshot("tests/.ditto", long_nodeid, "value", "pandas.parquet"),
            ReportedSnapshot(
                "tests/.ditto", "tests/test_a.py::test_short", "v", "json"
            ),
        ],
        updated=[],
        pruned=[],
        would_prune=[],
        console=Console(file=stream, width=width, color_system=None),
    )
    output = stream.getvalue()

    assert all(len(line) <= width for line in output.splitlines())
    assert "test_something[param]" in output
    assert "tests/test_a.py::test_short" in output


def test_report_names_a_pruned_snapshot_by_its_storage_name_under_its_target() -> None:
    """A prune deletes a snapshot the lock doesn't record, so it has no test."""
    stream = StringIO()

    render_session_report(
        created=[],
        updated=[],
        pruned=[PrunedSnapshot("tests/.ditto", "test_b@v~0123456789abcdef.json")],
        would_prune=[],
        console=Console(file=stream, width=80, color_system=None),
    )
    output = stream.getvalue()

    assert "tests/.ditto" in output
    assert "test_b@v~0123456789abcdef.json" in output
