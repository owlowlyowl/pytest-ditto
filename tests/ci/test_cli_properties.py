"""Property-based tests for pure CLI helper functions."""

from __future__ import annotations

import re

from hypothesis import given
from hypothesis import strategies as st

from ditto.cli._data import _human_size, _parse_snapshot_name
from ditto.cli._display import _build_colour_map
from ditto.recorders._contract import NAME_PATTERN
from ditto.snapshot import SnapshotKey, _flat_key

# ── _human_size ───────────────────────────────────────────────────────────────

_SIZE_FORMAT = re.compile(r"^\d+ B$|^\d+\.\d+ (KB|MB|GB|TB)$")


@given(st.integers(min_value=0, max_value=10**18))
def test_human_size_always_produces_a_valid_size_string(n: int) -> None:
    """_human_size always returns '<integer> B' or '<decimal> <unit>' for any
    non-negative size."""
    assert _SIZE_FORMAT.match(_human_size(n))


@given(st.integers(min_value=0, max_value=1023))
def test_human_size_preserves_exact_byte_value_below_one_kb(n: int) -> None:
    """Values under 1 KB are returned as the exact integer followed by 'B' with no
    decimal."""
    actual = _human_size(n)

    expected = f"{n} B"
    assert actual == expected


@given(st.integers(min_value=1024, max_value=1024**2 - 1))
def test_human_size_uses_kb_unit_in_kilobyte_range(n: int) -> None:
    """Values from 1 KB up to (but not including) 1 MB are always formatted in KB."""
    assert _human_size(n).endswith(" KB")


@given(st.integers(min_value=1024**2, max_value=1024**3 - 1))
def test_human_size_uses_mb_unit_in_megabyte_range(n: int) -> None:
    """Values from 1 MB up to (but not including) 1 GB are always formatted in MB."""
    assert _human_size(n).endswith(" MB")


@given(st.integers(min_value=1024**3, max_value=1024**4 - 1))
def test_human_size_uses_gb_unit_in_gigabyte_range(n: int) -> None:
    """Values from 1 GB up to (but not including) 1 TB are always formatted in GB."""
    assert _human_size(n).endswith(" GB")


@given(st.integers(min_value=1024**4, max_value=10**18))
def test_human_size_uses_tb_unit_at_and_above_one_tb(n: int) -> None:
    """Values at or above 1 TB are always formatted in TB, with no upper ceiling."""
    assert _human_size(n).endswith(" TB")


@given(st.integers(min_value=1024, max_value=10**18))
def test_human_size_scaled_value_has_exactly_one_decimal_place(n: int) -> None:
    """The numeric part of any KB/MB/GB/TB result always has exactly one decimal
    place."""
    result = _human_size(n)

    numeric_str = result.split()[0]
    assert re.match(r"^\d+\.\d$", numeric_str), (
        f"{result!r}: expected one decimal place in the numeric part"
    )


# ── _parse_snapshot_name ──────────────────────────────────────────────────────


@given(
    module=st.lists(
        st.from_regex(r"[a-z_]{1,12}", fullmatch=True), min_size=1, max_size=5
    ).map("/".join),
    group=st.text(min_size=1),
    key=st.text(),
    recorder=st.from_regex(NAME_PATTERN, fullmatch=True),
)
def test_parse_snapshot_name_recovers_the_recorder_and_labels(
    module: str, group: str, key: str, recorder: str
) -> None:
    """Whatever the test name and key hold, a stored name parses back to the
    exact recorder and to the label's two parts."""
    sk = SnapshotKey(module, group, key, recorder)
    module_prefix = module.replace("/", ".") + "."

    test, key_label, ext = _parse_snapshot_name(_flat_key(sk))

    assert ext == f".{recorder}"
    assert test.startswith(module_prefix)
    group_label = test.removeprefix(module_prefix)
    assert not {"@", "~"} & set(group_label + key_label)


@given(st.text(alphabet=st.characters(blacklist_characters="@")))
def test_parse_snapshot_name_without_at_sign_returns_empty_key_and_ext(
    filename: str,
) -> None:
    """A filename containing no '@' returns the whole string as group; key and ext
    are empty."""
    parsed_group, parsed_key, parsed_ext = _parse_snapshot_name(filename)

    assert parsed_group == filename
    assert parsed_key == ""
    assert parsed_ext == ""


@given(st.text())
def test_parse_snapshot_name_ext_is_always_empty_or_starts_with_dot(
    filename: str,
) -> None:
    """The parsed extension is either an empty string or a dot-prefixed string —
    never a bare word."""
    _, _, ext = _parse_snapshot_name(filename)

    assert ext == "" or ext.startswith(".")


# ── _build_colour_map ─────────────────────────────────────────────────────────


@given(st.lists(st.text(min_size=1), min_size=1))
def test_colour_map_contains_every_input_name(names: list[str]) -> None:
    """Every name passed in appears as a key in the returned colour map."""
    result = _build_colour_map(names)

    for name in names:
        assert name in result


@given(st.lists(st.text(min_size=1), min_size=1, unique=True))
def test_colour_map_assignment_is_independent_of_input_order(names: list[str]) -> None:
    """Colour assignments are identical regardless of the order names are supplied."""
    assert _build_colour_map(names) == _build_colour_map(list(reversed(names)))


@given(st.lists(st.text(min_size=1), min_size=1))
def test_colour_map_all_assigned_colours_are_strings(names: list[str]) -> None:
    """All values in the returned colour map are strings."""
    result = _build_colour_map(names)

    assert all(isinstance(colour, str) for colour in result.values())
