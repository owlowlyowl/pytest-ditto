"""Property-based tests for Snapshot key-tracking invariants."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ditto.exceptions import (
    DittoSnapshotNameCollisionError,
    DittoSnapshotNameTooLongError,
    DuplicateSnapshotKeyError,
)
from ditto.snapshot import (
    Snapshot,
    SnapshotKey,
    _flat_key,
    _label,
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
def test_file_name_after_the_module_is_portable(sk) -> None:
    """The name after the module has only portable ASCII characters."""
    name = _flat_key(sk).removeprefix(sk.module.replace("/", ".") + ".")

    assert name.isascii()
    assert not _NOT_PORTABLE & set(name)


# Module paths up to the longest that still leaves room for a label: a module
# prefix of 255 bytes less the hash, separators, recorder and 16 label
# characters. Segments hold non-ASCII too, since the module is a file path.
_long_module = st.lists(
    st.text(alphabet="abé_", min_size=1, max_size=60), min_size=1, max_size=6
).map("/".join)


@given(
    module=_long_module,
    group=st.text(min_size=1, max_size=300),
    key=st.text(max_size=300),
    identifier=st.sampled_from(["json", "pandas.parquet"]),
)
def test_whole_file_name_fits_in_255_bytes(module, group, key, identifier) -> None:
    """The whole file name, module prefix included, is at most 255 bytes, or
    naming it raises a clear error when the module leaves no room for a label."""
    sk = SnapshotKey(module, group, key, identifier)

    try:
        name = _flat_key(sk)
    except DittoSnapshotNameTooLongError:
        fixed = len(module.replace("/", ".").encode()) + 1 + 1 + 16 + 1
        assert fixed + len(identifier) + 16 > 255
    else:
        assert len(name.encode("utf-8")) <= 255


@given(
    module=_long_module,
    group=st.text(min_size=1, max_size=300),
    key=st.text(max_size=300),
    identifier=st.sampled_from(["json", "pandas.parquet"]),
)
def test_remote_key_is_not_limited_by_the_module_path(
    module, group, key, identifier
) -> None:
    """A remote key isn't a file name: any module path gets one, and its label
    keeps the usual 80 + 40 characters however long the module is."""
    sk = SnapshotKey(module, group, key, identifier)

    name = _remote_key(sk)

    assert name.startswith(module + "/")
    after_module = name.removeprefix(module + "/")
    assert len(after_module) <= 80 + 1 + 40 + 1 + 16 + 1 + len(identifier)
    assert after_module.startswith(_label(sk))


def test_a_long_module_works_with_a_remote_backend() -> None:
    """A deep test path too long for a file name still records and reads back
    through a remote backend."""
    module = "/".join(["pkg"] + [f"subdir_{i:02d}" for i in range(24)])
    backend: dict[str, bytes] = {}
    snapshot = Snapshot(
        target="memory://", _backend=backend, group_name="test_t", module=module
    )

    assert snapshot({"v": 1}, "k") == {"v": 1}

    (name,) = backend
    assert name.startswith(module + "/test_t@k~")
    with pytest.raises(DittoSnapshotNameTooLongError):
        _flat_key(SnapshotKey(module, "test_t", "k", "json"))


def test_a_long_module_shortens_the_label_rather_than_failing() -> None:
    """A module path that leaves only a little room still gets a name that fits,
    with the label shortened, where the unhashed format needed 250 bytes."""
    module = "/".join(["tests"] + ["d" * 60] * 3)
    sk = SnapshotKey(module, "test_" + "g" * 40, "k" * 10, "json")

    name = _flat_key(sk)

    assert len(name.encode()) <= 255
    assert name.startswith(module.replace("/", ".") + ".test_")


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
