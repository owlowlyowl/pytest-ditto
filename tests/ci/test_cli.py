"""Unit tests for pure CLI helper functions in ditto.cli."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock


from ditto.cli import (
    RecorderInfo,
    _build_colour_map,
    _ext_map,
    _human_size,
    _parse_snapshot_name,
    gather_stats,
)


# ── _parse_snapshot_name ──────────────────────────────────────────────────────


class TestParseSnapshotName:
    def test_splits_group_key_and_extension(self):
        """Standard {group}@{key}.{ext} filename is split correctly."""
        group, key, ext = _parse_snapshot_name("test_foo@result.pickle")
        assert group == "test_foo"
        assert key == "result"
        assert ext == ".pickle"

    def test_preserves_multi_dot_extension(self):
        """Extension with multiple dots (e.g. pandas.parquet) is preserved."""
        group, key, ext = _parse_snapshot_name("test_foo@result.pandas.parquet")
        assert group == "test_foo"
        assert key == "result"
        assert ext == ".pandas.parquet"

    def test_no_at_sign_returns_empty_key_and_ext(self):
        """A filename with no '@' is treated as group only; key and ext are empty."""
        group, key, ext = _parse_snapshot_name("invalid_filename")
        assert group == "invalid_filename"
        assert key == ""
        assert ext == ""

    def test_returns_empty_extension_when_no_dot_follows_at(self):
        """A file like 'group@key' (no dot) yields an empty ext."""
        group, key, ext = _parse_snapshot_name("test_foo@key_only")
        assert group == "test_foo"
        assert key == "key_only"
        assert ext == ""

    def test_preserves_dots_in_group_portion(self):
        """Group portion (before @) may itself contain dots (unittest class names)."""
        group, key, ext = _parse_snapshot_name("MyTestCase.test_method@snap.yaml")
        assert group == "MyTestCase.test_method"
        assert key == "snap"
        assert ext == ".yaml"


# ── _human_size ───────────────────────────────────────────────────────────────


class TestHumanSize:
    def test_formats_with_bytes_suffix_when_under_one_kb(self):
        assert _human_size(0) == "0 B"
        assert _human_size(512) == "512 B"
        assert _human_size(1023) == "1023 B"

    def test_formats_with_kb_suffix_at_kilobyte_boundary(self):
        assert _human_size(1024) == "1.0 KB"
        assert _human_size(2048) == "2.0 KB"

    def test_formats_with_mb_suffix_at_megabyte_boundary(self):
        assert _human_size(1024 * 1024) == "1.0 MB"

    def test_formats_with_gb_suffix_at_gigabyte_boundary(self):
        assert _human_size(1024**3) == "1.0 GB"

    def test_formats_with_tb_suffix_at_terabyte_boundary(self):
        assert _human_size(1024**4) == "1.0 TB"

    def test_formats_fractional_kilobytes(self):
        # 1536 bytes = 1.5 KB
        assert _human_size(1536) == "1.5 KB"


# ── _build_colour_map ─────────────────────────────────────────────────────────


class TestBuildColourMap:
    def test_empty_input_returns_empty_map(self):
        assert _build_colour_map([]) == {}

    def test_single_name_gets_first_palette_colour(self):
        result = _build_colour_map(["pickle"])
        assert "pickle" in result
        assert isinstance(result["pickle"], str)

    def test_assignment_is_deterministic_by_sorted_order(self):
        names = ["yaml", "pickle", "json"]
        result1 = _build_colour_map(names)
        result2 = _build_colour_map(reversed(names))
        # Same colour assignment regardless of input order
        assert result1 == result2

    def test_assigns_palette_colours_in_alphabetical_order(self):
        """First sorted name gets palette[0], second gets palette[1]."""
        from ditto.cli import _RECORDER_PALETTE

        result = _build_colour_map(["zz", "aa"])
        assert result["aa"] == _RECORDER_PALETTE[0]
        assert result["zz"] == _RECORDER_PALETTE[1]


# ── _ext_map ──────────────────────────────────────────────────────────────────


class TestExtMap:
    def test_maps_extension_to_recorder_info(self):
        infos = [
            RecorderInfo(name="pickle", extension=".pickle", package="pytest-ditto"),
            RecorderInfo(name="yaml", extension=".yaml", package="pytest-ditto"),
        ]
        result = _ext_map(infos)
        assert result[".pickle"].name == "pickle"
        assert result[".yaml"].name == "yaml"

    def test_empty_list_returns_empty_map(self):
        assert _ext_map([]) == {}

    def test_later_entry_wins_on_duplicate_extension(self):
        """Last info with a given extension is kept (dict overwrite semantics)."""
        a = RecorderInfo(name="first", extension=".pkl", package="pkg-a")
        b = RecorderInfo(name="second", extension=".pkl", package="pkg-b")
        result = _ext_map([a, b])
        assert result[".pkl"].name == "second"


# ── gather_stats ──────────────────────────────────────────────────────────────


def _mock_file(name: str, size: int, mtime: float) -> Path:
    """Return a Path-like mock with a working stat()."""
    p = MagicMock(spec=Path)
    p.name = name
    stat = MagicMock()
    stat.st_size = size
    stat.st_mtime = mtime
    p.stat.return_value = stat
    return p


class TestGatherStats:
    def test_attributes_file_to_recorder_when_extension_is_known(self):
        """A file with a mapped extension is attributed to its recorder."""
        f = _mock_file("test_foo@snap.pickle", size=100, mtime=1000.0)
        em = {".pickle": RecorderInfo("pickle", ".pickle", "pytest-ditto")}

        stats = gather_stats([f], em)

        assert stats.total_count == 1
        assert stats.total_size == 100
        assert "pickle" in stats.by_recorder
        assert stats.by_recorder["pickle"] == (1, 100)

    def test_unknown_extension_falls_back_to_raw_name(self):
        """An unmapped extension uses the extension (minus leading dot) as recorder name."""
        f = _mock_file("test_foo@snap.custom", size=50, mtime=500.0)

        stats = gather_stats([f], ext_map={})

        assert "custom" in stats.by_recorder

    def test_no_extension_uses_empty_string_key(self):
        """A file parsed with no extension falls into the '' recorder bucket."""
        f = _mock_file("invalid_filename", size=10, mtime=200.0)

        stats = gather_stats([f], ext_map={})

        assert "" in stats.by_recorder

    def test_tracks_oldest_and_newest_files_by_mtime(self):
        """oldest and newest are set to the files with the min/max mtime."""
        old_f = _mock_file("test_a@x.pickle", size=10, mtime=100.0)
        new_f = _mock_file("test_b@y.pickle", size=20, mtime=999.0)

        stats = gather_stats([old_f, new_f], ext_map={})

        assert stats.oldest[0] == 100.0
        assert stats.newest[0] == 999.0

    def test_aggregates_multiple_files_same_recorder(self):
        """Multiple files of the same recorder type are summed correctly."""
        files = [
            _mock_file("test_a@s.pickle", size=100, mtime=1.0),
            _mock_file("test_b@s.pickle", size=200, mtime=2.0),
            _mock_file("test_c@s.pickle", size=300, mtime=3.0),
        ]
        em = {".pickle": RecorderInfo("pickle", ".pickle", "pytest-ditto")}

        stats = gather_stats(files, em)

        assert stats.total_count == 3
        assert stats.total_size == 600
        assert stats.by_recorder["pickle"] == (3, 600)
