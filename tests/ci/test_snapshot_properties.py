"""Property-based tests for Snapshot filepath construction and key-tracking
invariants."""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from ditto import recorders
from ditto.exceptions import DuplicateSnapshotKeyError
from ditto.snapshot import Snapshot, session_tracker

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

_recorder_names = ["pickle", "json", "yaml"]

# tmp_path is reused across examples — safe because filepath() is pure and the
# snapshot tests reset session_tracker before each example. Suppress the check.
_no_fixture_reset = settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)

# ── Snapshot.filepath ─────────────────────────────────────────────────────────


@_no_fixture_reset
@given(
    key=_safe_key,
    recorder_name=st.sampled_from(_recorder_names),
)
def test_filepath_extension_always_matches_recorder_extension(
    tmp_path, key: str, recorder_name: str
) -> None:
    """The filepath for any key always ends with the configured recorder's extension."""
    recorder = recorders.get(recorder_name)
    snapshot = Snapshot(path=tmp_path, group_name="test", recorder=recorder)

    fp = snapshot.filepath(key)

    assert fp.name.endswith(f".{recorder.extension}")


@_no_fixture_reset
@given(key=_safe_key)
def test_filepath_parent_is_always_snapshot_path(tmp_path, key: str) -> None:
    """The filepath for any simple key is a direct child of snapshot.path — no
    subdirectories."""
    snapshot = Snapshot(path=tmp_path, group_name="test")

    fp = snapshot.filepath(key)

    assert fp.parent == tmp_path


# ── Duplicate key detection ───────────────────────────────────────────────────


@_no_fixture_reset
@given(key=_safe_key)
def test_duplicate_key_always_raises_on_second_call(tmp_path, key: str) -> None:
    """Calling snapshot twice with the same key always raises
    DuplicateSnapshotKeyError."""
    session_tracker.reset()
    snapshot = Snapshot(path=tmp_path, group_name="test")
    snapshot(1, key)

    with pytest.raises(DuplicateSnapshotKeyError):
        snapshot(2, key)


@_no_fixture_reset
@given(keys=st.lists(_safe_key, min_size=1, max_size=10, unique=True))
def test_unique_keys_never_trigger_duplicate_error(tmp_path, keys: list[str]) -> None:
    """Using a distinct key for each snapshot call never raises, regardless of how
    many calls are made."""
    session_tracker.reset()
    snapshot = Snapshot(path=tmp_path, group_name="test")

    for i, key in enumerate(keys):
        snapshot(i, key)
