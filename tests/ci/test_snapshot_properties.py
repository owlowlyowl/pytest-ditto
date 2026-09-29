"""Property-based tests for Snapshot key-tracking invariants."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ditto.exceptions import DittoSnapshotNameCollisionError, DuplicateSnapshotKeyError
from ditto.snapshot import (
    Snapshot,
    SnapshotKey,
    _flat_key,
    _remote_key,
    _SessionTracker,
)

# Keys safe for use as filesystem names on Linux: no path separators, null bytes,
# or surrogate characters (surrogates cannot be encoded as UTF-8 filenames).
# Providing an explicit alphabet overrides st.text()'s default surrogate exclusion,
# so the Cs category must be blacklisted explicitly.
# Length is capped so the full filename stays well under the 255-byte OS limit.
_safe_key = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(
        blacklist_characters="/\\\x00", blacklist_categories=("Cs",)
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


# ── Stored names ──────────────────────────────────────────────────────────────

# Test names come from parametrize IDs and keys are any string, so both are
# drawn from all of Unicode. Case variants, characters the label replaces and
# the label's own separators make matching labels (the case the hash exists
# for) likely.
_TOKENS = ["a", "A", "b", ".", "@", "~", "/", ":", "_", "é", "\x00", " "]
_part = st.one_of(
    st.lists(st.sampled_from(_TOKENS), max_size=8).map("".join), st.text(max_size=20)
)
_identity = st.builds(
    SnapshotKey,
    module=st.sampled_from(["m", "tests/test_api"]),
    group_name=_part,
    key=_part,
    identifier=st.sampled_from(["json", "pandas.parquet"]),
)
# Characters Windows forbids in file names, and the path separators.
_NOT_PORTABLE = set('<>:"/\\|?*') | {chr(c) for c in range(32)}


@given(sk=_identity)
def test_file_name_after_the_module_is_portable_and_bounded(sk) -> None:
    """The name after the module has only portable ASCII characters and is at
    most 80 + 40 characters of label plus the separators, hash and recorder."""
    name = _flat_key(sk).removeprefix(sk.module.replace("/", ".") + ".")

    assert name.isascii()
    assert not _NOT_PORTABLE & set(name)
    assert len(name) <= 80 + 1 + 40 + 1 + 8 + 1 + len(sk.identifier)


@given(a=_identity, b=_identity)
def test_distinct_identities_get_names_distinct_ignoring_case(a, b) -> None:
    """Two different snapshots never share a name, even on a case-insensitive
    file system. (A shared 8-hex-character hash is possible in principle; a
    session reports one as a collision.)"""
    if a != b:
        assert _flat_key(a).casefold() != _flat_key(b).casefold()
        assert _remote_key(a).casefold() != _remote_key(b).casefold()


def test_two_snapshots_with_one_name_are_reported(monkeypatch) -> None:
    """If two different snapshots' names collide, the second one raises an error
    naming both, rather than reading or overwriting the first's baseline."""
    monkeypatch.setattr("ditto.snapshot._identity_hash", lambda sk: "00000000")
    backend: dict[str, bytes] = {}
    tracker = _SessionTracker()

    def snapshot_for(group_name: str) -> Snapshot:
        return Snapshot(
            target="memory://",
            _backend=backend,
            group_name=group_name,
            module="m",
            _tracker=tracker,
        )

    # `:` and `_` give the same label; with the hash forced equal, the same name.
    snapshot_for("test_t[a:b]")(1, "k")

    with pytest.raises(DittoSnapshotNameCollisionError, match=r"test_t\[a:b\]"):
        snapshot_for("test_t[a_b]")(2, "k")
