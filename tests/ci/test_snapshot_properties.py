"""Property-based tests for Snapshot key-tracking invariants."""

from __future__ import annotations

from urllib.parse import unquote

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ditto.exceptions import DuplicateSnapshotKeyError
from ditto.snapshot import Snapshot, SnapshotKey, _flat_key

# Keys a snapshot accepts: no `@`, path separators or control characters, and
# no surrogates (which can't be encoded as UTF-8). Providing an explicit
# alphabet overrides st.text()'s default surrogate exclusion, so the Cs category
# must be blacklisted explicitly. Length is capped so the full filename stays
# well under the 255-byte OS limit.
_safe_key = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(
        blacklist_characters="@/\\", blacklist_categories=("Cc", "Cs")
    ),
)


def _memory_snapshot(**kwargs) -> Snapshot:
    """Create a memory:// Snapshot backed by a plain dict for duplicate-key tests."""
    return Snapshot(
        target="memory://",
        _backend={},
        group_name=kwargs.pop("group_name", "test"),
        module=kwargs.pop("module", "m"),
        **kwargs,
    )


# ── Duplicate key detection ───────────────────────────────────────────────────


@given(key=_safe_key)
def test_duplicate_key_always_raises_on_second_call(key: str) -> None:
    """Calling snapshot twice with one key raises DuplicateSnapshotKeyError."""
    snapshot = _memory_snapshot()
    snapshot(1, key)

    with pytest.raises(DuplicateSnapshotKeyError):
        snapshot(2, key)


@given(keys=st.lists(_safe_key, min_size=1, max_size=10, unique=True))
def test_unique_keys_never_trigger_duplicate_error(keys: list[str]) -> None:
    """Distinct keys never trigger the duplicate-key error."""
    snapshot = _memory_snapshot()

    for i, key in enumerate(keys):
        snapshot(i, key)


# ── Storage keys ──────────────────────────────────────────────────────────────

# Group names come from test names and their parametrize IDs, so they can hold
# anything. Building them from separators, characters Windows forbids and the
# percent-encoded forms of those characters makes near-collisions (`:` against
# a literal `%3A`, an `@` in the group against the key's `@`) easy to find.
_KEY_TOKENS = ["a", "b", ".", "[", "]", "%", ":", "%3A", "*", "%2A", "%25", "%2F"]
_GROUP_TOKENS = [*_KEY_TOKENS, "@", "/", "\\", "%5C", "\x01", "%01"]
_group = st.lists(st.sampled_from(_GROUP_TOKENS), max_size=6).map("".join)
_key = st.lists(st.sampled_from(_KEY_TOKENS), min_size=1, max_size=4).map("".join)
_KEY_FORMATS = pytest.mark.parametrize(
    "key_of", [_flat_key, str], ids=["file", "remote"]
)
# Characters that can't appear in a file name on Windows, or on any platform (`/`).
_NOT_PORTABLE = set('<>:"/\\|?*') | {chr(c) for c in range(32)}


@_KEY_FORMATS
@given(a=st.tuples(_group, _key), b=st.tuples(_group, _key))
def test_distinct_groups_and_keys_give_distinct_storage_keys(key_of, a, b) -> None:
    """Two snapshots of one test file and recorder share a storage key only if
    their group name and key are both equal."""
    key_a = key_of(SnapshotKey("tests/test_m", *a, "json"))
    key_b = key_of(SnapshotKey("tests/test_m", *b, "json"))

    assert (key_a == key_b) == (a == b)


@given(group=_group, key=_key)
def test_file_storage_key_decodes_to_its_group_and_key(group, key) -> None:
    """A file storage key splits at its last `@` and decodes back to its parts."""
    name = _flat_key(SnapshotKey("tests/test_m", group, key, "json"))

    head, _, tail = name.rpartition("@")
    encoded_key = tail.removesuffix(".json")

    assert unquote(head.removeprefix("tests.test_m.")) == group
    assert unquote(encoded_key) == key


@given(group=_group, key=_key)
def test_file_storage_key_is_a_portable_file_name(group, key) -> None:
    """A file storage key has no character a Windows (or any) file name forbids."""
    name = _flat_key(SnapshotKey("tests/test_m", group, key, "json"))

    assert not _NOT_PORTABLE & set(name)


@given(
    group=st.text(alphabet="abc_.[]-=@ ", max_size=12),
    key=st.text(alphabet="abc_.[]-= ", min_size=1, max_size=8),
)
def test_file_storage_key_leaves_portable_names_unchanged(group, key) -> None:
    """Names without `%` or unportable characters are stored exactly as before."""
    name = _flat_key(SnapshotKey("tests/test_m", group, key, "json"))

    assert name == f"tests.test_m.{group}@{key}.json"


@given(
    key=st.builds(
        lambda head, bad, tail: head + bad + tail,
        _safe_key,
        st.sampled_from(["@", "/", "\\", "\x00", "\n", "\x1f"]),
        _safe_key,
    )
)
def test_key_with_a_forbidden_character_is_rejected(key) -> None:
    """Keys can't contain `@`, a path separator or a control character."""
    snapshot = _memory_snapshot()

    with pytest.raises(ValueError, match="keys can't contain"):
        snapshot(1, key)
