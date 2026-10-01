"""The CLI's output at a normal terminal width: identity, grouping, no truncation.

Covers the redesign in #182: one way to name a snapshot, relative paths,
wrapping in the middle instead of truncating, and every view built as a Rich
table that fits the width it is given.
"""

import re
from io import StringIO

import pytest
from rich.console import Console

from ditto._inventory import location_key
from ditto._lockfile import LockEntry
from ditto._manifest import BackendManifest, LocatedEntry, ManifestEntry
from ditto._report import PrunedSnapshot, ReportedSnapshot, render_session_report
from ditto.cli._data import RecorderInfo
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


def rows_of(output: str) -> list[str]:
    """The lines inside the table's frame, with the frame characters removed."""
    return [line.strip("│ ").rstrip() for line in output.splitlines() if "│" in line]


# ── every view fits the width, and nothing is truncated ──────────────────────


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("flat", [False, True])
def test_list_never_exceeds_the_width(width: int, flat: bool) -> None:
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
        flat=flat,
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


@pytest.mark.parametrize("width", WIDTHS)
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
    first_column = re.sub(r"\s+", "", "".join(
        line.split("│")[1] for line in output.splitlines() if line.startswith("│")
    ))

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


def test_flat_keeps_the_whole_node_id_on_one_row() -> None:
    """`--flat` gives one row per snapshot with nothing grouped away."""
    nodeid = "tests/test_a.py::test_x[::]"
    stored = "test_a@k~0123456789abcdef.json"

    output = render(
        _render_snapshots,
        manifest_of((stored, nodeid)),
        identities_of((stored, nodeid)),
        INFOS,
        width=120,
        flat=True,
    )

    assert nodeid in output
    assert not any("├─ " in row for row in rows_of(output))
    assert not any("└─ " in row for row in rows_of(output))


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

    output = render(
        _render_snapshots, [manifest], None, INFOS, width=120
    )

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
