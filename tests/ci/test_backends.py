"""Behavioural tests for LocalMapping, TransformMapping, and PrefixedMapping."""

from __future__ import annotations

import pickle
from collections.abc import MutableMapping
from pathlib import Path

import pytest

from ditto.backends import LocalMapping, PrefixedMapping, TransformMapping
from ditto.backends._transform import _make_recorder_transform
from ditto.recorders import default as _default_recorder


# ---------------------------------------------------------------------------
# LocalMapping
# ---------------------------------------------------------------------------


def test_local_mapping_stores_and_retrieves_bytes(tmp_path: Path) -> None:
    """Bytes written under a key are returned unchanged on read."""
    m = LocalMapping(tmp_path)

    m["snap.pkl"] = b"hello"

    assert m["snap.pkl"] == b"hello"


def test_local_mapping_raises_key_error_for_absent_key(tmp_path: Path) -> None:
    """Reading a key that was never written raises KeyError."""
    m = LocalMapping(tmp_path)

    with pytest.raises(KeyError):
        _ = m["missing.pkl"]


def test_local_mapping_creates_directory_on_first_write(tmp_path: Path) -> None:
    """The root directory is created lazily on the first write, not at construction."""
    root = tmp_path / "new" / ".ditto"
    m = LocalMapping(root)

    assert not root.exists()

    m["snap.pkl"] = b"data"

    assert root.is_dir()


def test_local_mapping_contains_written_key(tmp_path: Path) -> None:
    """__contains__ returns True for a key that has been written."""
    m = LocalMapping(tmp_path)
    m["a.pkl"] = b"x"

    assert "a.pkl" in m


def test_local_mapping_does_not_contain_absent_key(tmp_path: Path) -> None:
    """__contains__ returns False for a key that has never been written."""
    m = LocalMapping(tmp_path)

    assert "nope.pkl" not in m


def test_local_mapping_deletes_key(tmp_path: Path) -> None:
    """Deleting a key removes it from the mapping."""
    m = LocalMapping(tmp_path)
    m["a.pkl"] = b"x"

    del m["a.pkl"]

    assert "a.pkl" not in m


def test_local_mapping_delete_absent_key_raises(tmp_path: Path) -> None:
    """Deleting a key that does not exist raises KeyError."""
    m = LocalMapping(tmp_path)

    with pytest.raises(KeyError):
        del m["ghost.pkl"]


def test_local_mapping_iter_returns_filenames(tmp_path: Path) -> None:
    """__iter__ yields the filenames of all stored keys."""
    m = LocalMapping(tmp_path)
    m["a.pkl"] = b"1"
    m["b.pkl"] = b"2"

    assert set(m) == {"a.pkl", "b.pkl"}


def test_local_mapping_len_counts_stored_keys(tmp_path: Path) -> None:
    """__len__ returns the number of stored files."""
    m = LocalMapping(tmp_path)
    m["a.pkl"] = b"1"
    m["b.pkl"] = b"2"

    assert len(m) == 2


def test_local_mapping_iter_returns_empty_when_directory_does_not_exist(
    tmp_path: Path,
) -> None:
    """__iter__ on a non-existent root yields nothing rather than raising."""
    m = LocalMapping(tmp_path / "nonexistent")

    assert list(m) == []
    assert len(m) == 0


def test_local_mapping_handles_bracket_characters_in_key(tmp_path: Path) -> None:
    """Keys with bracket characters are stored and retrieved literally, not as globs."""
    m = LocalMapping(tmp_path)
    key = "test_result[second]@v.pkl"

    m[key] = b"payload"

    assert m[key] == b"payload"
    assert key in m


# ---------------------------------------------------------------------------
# TransformMapping
# ---------------------------------------------------------------------------


def test_transform_mapping_stores_and_retrieves_via_recorder(tmp_path: Path) -> None:
    """Values written through a recorder transform round-trip correctly."""
    store = TransformMapping(mapping=LocalMapping(tmp_path)) | _make_recorder_transform(
        _default_recorder()
    )

    store["key.pkl"] = {"x": 42}

    actual = store["key.pkl"]
    assert actual == {"x": 42}


def test_transform_mapping_contains_does_not_deserialise(tmp_path: Path) -> None:
    """__contains__ resolves without calling __getitem__ or the load callable.

    This is the critical correctness guarantee: a load callable that parses a
    large file must not run just to check key existence.
    """
    load_calls: list[str] = []

    def counting_load(raw: bytes) -> object:
        load_calls.append("load")
        return pickle.loads(raw)  # noqa: S301

    backend = LocalMapping(tmp_path)
    backend["k.pkl"] = pickle.dumps("value")
    store = TransformMapping(
        mapping=backend,
        save=pickle.dumps,
        load=counting_load,
    )

    _ = "k.pkl" in store

    assert load_calls == [], "load callable must not be invoked by __contains__"


def test_transform_mapping_pipe_combines_mapping_and_transform(tmp_path: Path) -> None:
    """| combines a backend wrapper with a recorder transform into a usable store."""
    store = TransformMapping(mapping=LocalMapping(tmp_path)) | _make_recorder_transform(
        _default_recorder()
    )

    store["k.pkl"] = [1, 2, 3]

    assert store["k.pkl"] == [1, 2, 3]


def test_transform_mapping_missing_key_raises(tmp_path: Path) -> None:
    """Reading an absent key raises KeyError (propagated from the inner mapping)."""
    store = TransformMapping(mapping=LocalMapping(tmp_path)) | _make_recorder_transform(
        _default_recorder()
    )

    with pytest.raises(KeyError):
        _ = store["missing.pkl"]


# ---------------------------------------------------------------------------
# PrefixedMapping
# ---------------------------------------------------------------------------


def test_prefixed_mapping_stores_with_prefix(tmp_path: Path) -> None:
    """Keys are stored under the prefixed form in the inner mapping."""
    inner: dict[str, bytes] = {}
    m = PrefixedMapping(inner, prefix="ns:")

    m["key"] = b"val"

    assert "ns:key" in inner
    assert "key" not in inner


def test_prefixed_mapping_retrieves_without_prefix(tmp_path: Path) -> None:
    """Values stored under a prefixed key are retrievable via the bare key."""
    inner: dict[str, bytes] = {"ns:key": b"val"}
    m = PrefixedMapping(inner, prefix="ns:")

    assert m["key"] == b"val"


def test_prefixed_mapping_contains_checks_prefixed_key(tmp_path: Path) -> None:
    """__contains__ looks up the prefixed form in the inner mapping."""
    inner: dict[str, bytes] = {"ns:key": b"val"}
    m = PrefixedMapping(inner, prefix="ns:")

    assert "key" in m
    assert "ns:key" not in m


def test_prefixed_mapping_iter_strips_prefix(tmp_path: Path) -> None:
    """__iter__ yields bare keys, stripping the prefix."""
    inner: dict[str, bytes] = {"ns:a": b"1", "ns:b": b"2", "other:c": b"3"}
    m = PrefixedMapping(inner, prefix="ns:")

    assert set(m) == {"a", "b"}


def test_prefixed_mapping_delete_removes_prefixed_key(tmp_path: Path) -> None:
    """Deleting a key removes the prefixed form from the inner mapping."""
    inner: dict[str, bytes] = {"ns:key": b"val"}
    m = PrefixedMapping(inner, prefix="ns:")

    del m["key"]

    assert "ns:key" not in inner


def test_prefixed_mapping_empty_prefix_raises() -> None:
    """Constructing with an empty prefix raises ValueError."""
    with pytest.raises(ValueError):
        PrefixedMapping({}, prefix="")


def test_prefixed_mapping_propagates_context_manager_enter() -> None:
    """__enter__ is forwarded to an inner store that is an AbstractContextManager."""

    class TrackingStore(MutableMapping[str, bytes]):
        entered = False
        exited = False

        def __enter__(self) -> "TrackingStore":
            self.entered = True
            return self

        def __exit__(self, *_: object) -> None:
            self.exited = True

        def __getitem__(self, k: str) -> bytes: ...
        def __setitem__(self, k: str, v: bytes) -> None: ...
        def __delitem__(self, k: str) -> None: ...
        def __iter__(self):
            return iter([])

        def __len__(self) -> int:
            return 0

    inner = TrackingStore()
    m = PrefixedMapping(inner, prefix="p:")

    with m:
        assert inner.entered is True
    assert inner.exited is True


def test_prefixed_mapping_does_not_fail_when_inner_has_no_context_manager() -> None:
    """__enter__/__exit__ on a plain dict inner store does not raise."""
    m = PrefixedMapping({}, prefix="p:")

    with m:
        m["k"] = b"v"

    assert m["k"] == b"v"
