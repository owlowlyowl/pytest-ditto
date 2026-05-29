"""Unit tests for pure CLI helper functions in ditto.cli."""

from __future__ import annotations

from click.testing import CliRunner

from ditto import cli as cli_mod
from ditto._manifest import BackendManifest, ManifestEntry
from ditto.cli import (
    _RECORDER_PALETTE,
    RecorderInfo,
    _build_colour_map,
    _ext_map,
    _human_size,
    _parse_snapshot_name,
    cli,
    gather_stats,
)


# ── _parse_snapshot_name ──────────────────────────────────────────────────────


def test_splits_group_key_and_extension() -> None:
    """Standard {group}@{key}.{ext} filename is split correctly."""
    group, key, ext = _parse_snapshot_name("test_foo@result.pickle")
    assert group == "test_foo"
    assert key == "result"
    assert ext == ".pickle"


def test_preserves_multi_dot_extension() -> None:
    """Extension with multiple dots (e.g. pandas.parquet) is preserved."""
    group, key, ext = _parse_snapshot_name("test_foo@result.pandas.parquet")
    assert group == "test_foo"
    assert key == "result"
    assert ext == ".pandas.parquet"


def test_no_at_sign_returns_empty_key_and_ext() -> None:
    """A filename with no '@' is treated as group only; key and ext are empty."""
    group, key, ext = _parse_snapshot_name("invalid_filename")
    assert group == "invalid_filename"
    assert key == ""
    assert ext == ""


def test_returns_empty_extension_when_no_dot_follows_at() -> None:
    """A file like 'group@key' (no dot) yields an empty ext."""
    group, key, ext = _parse_snapshot_name("test_foo@key_only")
    assert group == "test_foo"
    assert key == "key_only"
    assert ext == ""


def test_preserves_dots_in_group_portion() -> None:
    """Group portion (before @) may itself contain dots (unittest class names)."""
    group, key, ext = _parse_snapshot_name("MyTestCase.test_method@snap.yaml")
    assert group == "MyTestCase.test_method"
    assert key == "snap"
    assert ext == ".yaml"


# ── _human_size ───────────────────────────────────────────────────────────────


def test_formats_with_bytes_suffix_when_under_one_kb() -> None:
    """Values below 1 KB are rendered with a plain byte suffix."""
    assert _human_size(0) == "0 B"
    assert _human_size(512) == "512 B"
    assert _human_size(1023) == "1023 B"


def test_formats_with_kb_suffix_at_kilobyte_boundary() -> None:
    """Values at or above 1 KB are rendered in kilobytes."""
    assert _human_size(1024) == "1.0 KB"
    assert _human_size(2048) == "2.0 KB"


def test_formats_with_mb_suffix_at_megabyte_boundary() -> None:
    """Values at the megabyte boundary are rendered in megabytes."""
    assert _human_size(1024 * 1024) == "1.0 MB"


def test_formats_with_gb_suffix_at_gigabyte_boundary() -> None:
    """Values at the gigabyte boundary are rendered in gigabytes."""
    assert _human_size(1024**3) == "1.0 GB"


def test_formats_with_tb_suffix_at_terabyte_boundary() -> None:
    """Values at the terabyte boundary are rendered in terabytes."""
    assert _human_size(1024**4) == "1.0 TB"


def test_formats_fractional_kilobytes() -> None:
    """A sub-kilobyte fraction is rendered to one decimal place (1536 B = 1.5 KB)."""
    assert _human_size(1536) == "1.5 KB"


# ── _build_colour_map ─────────────────────────────────────────────────────────


def test_colour_map_is_empty_for_no_names() -> None:
    """An empty name iterable produces an empty colour map."""
    assert _build_colour_map([]) == {}


def test_single_name_gets_a_palette_colour() -> None:
    """A single name is assigned a string palette colour."""
    result = _build_colour_map(["pickle"])
    assert "pickle" in result
    assert isinstance(result["pickle"], str)


def test_colour_assignment_is_independent_of_input_order() -> None:
    """The same names yield the same colour assignment regardless of order."""
    names = ["yaml", "pickle", "json"]
    assert _build_colour_map(names) == _build_colour_map(list(reversed(names)))


def test_assigns_palette_colours_in_alphabetical_order() -> None:
    """First sorted name gets palette[0], second gets palette[1]."""
    result = _build_colour_map(["zz", "aa"])
    assert result["aa"] == _RECORDER_PALETTE[0]
    assert result["zz"] == _RECORDER_PALETTE[1]


# ── _ext_map ──────────────────────────────────────────────────────────────────


def test_maps_extension_to_recorder_info() -> None:
    """Each RecorderInfo is keyed by its extension."""
    infos = [
        RecorderInfo(name="pickle", extension=".pickle", package="pytest-ditto"),
        RecorderInfo(name="yaml", extension=".yaml", package="pytest-ditto"),
    ]
    result = _ext_map(infos)
    assert result[".pickle"].name == "pickle"
    assert result[".yaml"].name == "yaml"


def test_ext_map_is_empty_for_no_infos() -> None:
    """An empty info list produces an empty extension map."""
    assert _ext_map([]) == {}


def test_later_entry_wins_on_duplicate_extension() -> None:
    """Last info with a given extension is kept (dict overwrite semantics)."""
    a = RecorderInfo(name="first", extension=".pkl", package="pkg-a")
    b = RecorderInfo(name="second", extension=".pkl", package="pkg-b")
    result = _ext_map([a, b])
    assert result[".pkl"].name == "second"


# ── gather_stats ──────────────────────────────────────────────────────────────


def test_attributes_entry_to_recorder_when_extension_is_known() -> None:
    """An entry with a mapped extension is attributed to its recorder."""
    em = {".pickle": RecorderInfo("pickle", ".pickle", "pytest-ditto")}
    entries = [ManifestEntry("test_foo@snap.pickle", size_bytes=100, modified=1000.0)]

    stats = gather_stats(entries, em)

    assert stats.total_count == 1
    assert stats.total_size == 100
    assert stats.by_recorder["pickle"] == (1, 100)


def test_attributes_unknown_extension_to_its_raw_name() -> None:
    """An unmapped extension uses the extension (minus leading dot) as recorder name."""
    entries = [ManifestEntry("test_foo@snap.custom", size_bytes=50, modified=None)]

    stats = gather_stats(entries, ext_map={})

    assert "custom" in stats.by_recorder


def test_buckets_entry_with_no_extension_under_empty_string() -> None:
    """An entry parsed with no extension falls into the '' recorder bucket."""
    entries = [ManifestEntry("invalid_name", size_bytes=10, modified=None)]

    stats = gather_stats(entries, ext_map={})

    assert "" in stats.by_recorder


def test_tracks_oldest_and_newest_by_mtime_when_present() -> None:
    """oldest and newest are the entries with the min/max modified timestamp."""
    entries = [
        ManifestEntry("test_a@x.pickle", size_bytes=10, modified=100.0),
        ManifestEntry("test_b@y.pickle", size_bytes=20, modified=999.0),
    ]

    stats = gather_stats(entries, ext_map={})

    assert stats.oldest[0] == 100.0
    assert stats.newest[0] == 999.0


def test_leaves_oldest_and_newest_unset_when_no_entry_has_mtime() -> None:
    """Remote entries (modified=None) leave oldest/newest as None."""
    entries = [ManifestEntry("test_a@x.pickle", size_bytes=10, modified=None)]

    stats = gather_stats(entries, ext_map={})

    assert stats.oldest is None
    assert stats.newest is None


def test_sums_count_and_size_across_entries_of_one_recorder() -> None:
    """Multiple entries of the same recorder type are summed correctly."""
    em = {".pickle": RecorderInfo("pickle", ".pickle", "pytest-ditto")}
    entries = [
        ManifestEntry("test_a@s.pickle", size_bytes=100, modified=1.0),
        ManifestEntry("test_b@s.pickle", size_bytes=200, modified=2.0),
        ManifestEntry("test_c@s.pickle", size_bytes=300, modified=3.0),
    ]

    stats = gather_stats(entries, em)

    assert stats.total_count == 3
    assert stats.total_size == 600
    assert stats.by_recorder["pickle"] == (3, 600)


# ── command inventory dispatch ─────────────────────────────────────────────────


def _patch_inventory(monkeypatch, manifest: list[BackendManifest]) -> None:
    monkeypatch.setattr(cli_mod, "run_introspect", lambda path: manifest)


def test_list_renders_snapshots_from_the_manifest(tmp_path, monkeypatch) -> None:
    """`ditto list` renders the storage keys the introspection pass enumerated."""
    manifest = [
        BackendManifest("file:///x/.ditto", [ManifestEntry("mod.test_y@v.json", 7, None)])
    ]
    _patch_inventory(monkeypatch, manifest)

    result = CliRunner().invoke(cli, ["list", str(tmp_path)])

    assert result.exit_code == 0
    assert "test_y" in result.output


def test_stats_shows_a_configured_backend_even_with_no_snapshots(
    tmp_path, monkeypatch
) -> None:
    """An empty-but-resolved backend still appears in `ditto stats`, flagging it to
    the user as removable or misconfigured."""
    manifest = [BackendManifest("redis://h/0", [])]
    _patch_inventory(monkeypatch, manifest)

    result = CliRunner().invoke(cli, ["stats", str(tmp_path)])

    assert result.exit_code == 0
    assert "redis://h/0" in result.output


def test_list_reports_failure_and_exits_one_when_introspection_errors(
    tmp_path, monkeypatch
) -> None:
    """A failed introspection pass surfaces an error and a non-zero exit."""

    def _boom(path):
        raise cli_mod.IntrospectError("pytest blew up")

    monkeypatch.setattr(cli_mod, "run_introspect", _boom)

    result = CliRunner().invoke(cli, ["list", str(tmp_path)])

    assert result.exit_code == 1
    assert "Introspection failed" in result.output
