"""Property-based tests for Snapshot key-tracking invariants."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ditto.exceptions import DuplicateSnapshotKeyError
from ditto.snapshot import Snapshot, SnapshotKey, session_tracker

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
    """Calling snapshot twice with the same key always raises DuplicateSnapshotKeyError."""
    session_tracker.reset_keys()
    snapshot = _memory_snapshot()
    snapshot(1, key)

    with pytest.raises(DuplicateSnapshotKeyError):
        snapshot(2, key)


@given(keys=st.lists(_safe_key, min_size=1, max_size=10, unique=True))
def test_unique_keys_never_trigger_duplicate_error(keys: list[str]) -> None:
    """Using a distinct key for each snapshot call never raises, regardless of how many calls are made."""
    session_tracker.reset_keys()
    snapshot = _memory_snapshot()

    for i, key in enumerate(keys):
        snapshot(i, key)


def test_reset_keys_does_not_clear_session_level_created_list() -> None:
    """reset_keys() must not clear `created` or `updated` — those are session-level accumulators.

    Regression: reset_keys() previously cleared both lists, so any snapshots
    created by ordinary tests before a Hypothesis test ran were wiped from the
    report when the first Hypothesis example called reset_keys().
    """
    session_tracker.reset()
    sk = SnapshotKey(module="m", group_name="g", key="k", extension="pkl")
    session_tracker.created.append(sk)
    session_tracker.updated.append(sk)

    session_tracker.reset_keys()

    assert session_tracker.created == [sk]
    assert session_tracker.updated == [sk]
    session_tracker.reset()
