"""Behavioural tests for FsspecMapping, TransformMapping, and PrefixedMapping."""

from __future__ import annotations

import pickle
import uuid
from collections.abc import Iterator, MutableMapping

import pytest
from fsspec.implementations.memory import MemoryFileSystem

from ditto.backends import FsspecMapping, PrefixedMapping, TransformMapping
from ditto.backends._transform import _make_recorder_transform
from ditto.recorders import default as _default_recorder


def _mem() -> FsspecMapping:
    """FsspecMapping backed by an in-memory filesystem with a unique root.

    MemoryFileSystem uses a class-level store, so each call uses a distinct
    root path to prevent test pollution.
    """
    return FsspecMapping(MemoryFileSystem(skip_instance_cache=True), f"/{uuid.uuid4().hex}")


# ---------------------------------------------------------------------------
# FsspecMapping
# ---------------------------------------------------------------------------


def test_fsspec_mapping_stores_and_retrieves_bytes() -> None:
    """Bytes written under a key are returned unchanged on read."""
    m = _mem()

    m["snap.pkl"] = b"hello"

    assert m["snap.pkl"] == b"hello"


def test_fsspec_mapping_raises_key_error_for_absent_key() -> None:
    """Reading a key that was never written raises KeyError."""
    m = _mem()

    with pytest.raises(KeyError):
        _ = m["missing.pkl"]


def test_fsspec_mapping_contains_written_key() -> None:
    """__contains__ returns True for a key that has been written."""
    m = _mem()
    m["a.pkl"] = b"x"

    assert "a.pkl" in m


def test_fsspec_mapping_does_not_contain_absent_key() -> None:
    """__contains__ returns False for a key that has never been written."""
    m = _mem()

    assert "nope.pkl" not in m


def test_fsspec_mapping_deletes_key() -> None:
    """Deleting a key removes it from the mapping."""
    m = _mem()
    m["a.pkl"] = b"x"

    del m["a.pkl"]

    assert "a.pkl" not in m


def test_fsspec_mapping_delete_absent_key_raises() -> None:
    """Deleting a key that does not exist raises KeyError."""
    m = _mem()

    with pytest.raises(KeyError):
        del m["ghost.pkl"]


def test_fsspec_mapping_iter_returns_filenames() -> None:
    """__iter__ yields the filenames of all stored keys."""
    m = _mem()
    m["a.pkl"] = b"1"
    m["b.pkl"] = b"2"

    assert set(m) == {"a.pkl", "b.pkl"}


def test_fsspec_mapping_len_counts_stored_keys() -> None:
    """__len__ returns the number of stored entries."""
    m = _mem()
    m["a.pkl"] = b"1"
    m["b.pkl"] = b"2"

    assert len(m) == 2


def test_fsspec_mapping_iter_returns_empty_when_root_does_not_exist() -> None:
    """__iter__ on a non-existent root yields nothing rather than raising."""
    m = _mem()  # fresh unique root — nothing written, so root does not exist yet

    assert list(m) == []
    assert len(m) == 0


def test_fsspec_mapping_stores_and_retrieves_bracket_key() -> None:
    """Keys containing bracket characters round-trip correctly."""
    m = _mem()
    key = "test_result[second]@v.pkl"

    m[key] = b"payload"

    assert m[key] == b"payload"
    assert key in m


def test_fsspec_mapping_iter_includes_bracket_key() -> None:
    """Keys containing bracket characters are yielded by __iter__, not silently dropped.

    This is the regression FsspecMapping exists to fix: fsspec.FSMap.__iter__
    calls fs.glob() which uses fnmatch to expand [bracket] as a character-class
    pattern, silently dropping parametrised test names like test_result[second].
    """
    m = _mem()
    key = "test_result[second]@v.pkl"

    m[key] = b"payload"

    assert key in set(m)


def test_fsspec_mapping_stores_and_retrieves_bytes_at_nested_key_path() -> None:
    """Bytes stored under a slash-containing key are returned unchanged on read."""
    m = _mem()
    key = "tests/test_api/test_something@result.pkl"

    m[key] = b"nested-data"

    assert m[key] == b"nested-data"
    assert key in m


def test_fsspec_mapping_iter_yields_forward_slash_keys_for_nested_files() -> None:
    """__iter__ yields forward-slash-separated relative paths for files at any depth."""
    m = _mem()
    m["flat.pkl"] = b"1"
    m["sub/nested.pkl"] = b"2"
    m["sub/deep/leaf.pkl"] = b"3"

    keys = set(m)

    assert keys == {"flat.pkl", "sub/nested.pkl", "sub/deep/leaf.pkl"}
    assert all("\\" not in k for k in keys)


def test_fsspec_mapping_removes_entry_when_nested_key_is_deleted() -> None:
    """Deleting a nested key removes the backing entry."""
    m = _mem()
    key = "mod/group@k.pkl"
    m[key] = b"x"

    del m[key]

    assert key not in m


def test_fsspec_mapping_raises_when_key_contains_path_traversal() -> None:
    """A key that resolves outside the root raises ValueError."""
    m = _mem()

    with pytest.raises(ValueError, match="escape"):
        m["../../outside.pkl"] = b"x"


def test_fsspec_mapping_raises_when_key_is_absolute_path() -> None:
    """An absolute path key raises ValueError regardless of the path it names."""
    m = _mem()

    with pytest.raises(ValueError, match="absolute"):
        m["/etc/passwd"] = b"x"


def test_fsspec_mapping_raises_when_key_resolves_to_root() -> None:
    """A key of '.' resolves to the root directory itself and raises ValueError.

    posixpath.normpath('/root/.') == '/root', so without an explicit check
    the key would pass the traversal guard and attempt to open the root
    directory as a file, producing IsADirectoryError instead of ValueError.
    """
    m = _mem()

    with pytest.raises(ValueError):
        m["."] = b"x"


# ---------------------------------------------------------------------------
# TransformMapping
# ---------------------------------------------------------------------------


def test_transform_mapping_stores_and_retrieves_via_recorder() -> None:
    """Values written through a recorder transform round-trip correctly."""
    store = TransformMapping(mapping=_mem()) | _make_recorder_transform(
        _default_recorder()
    )

    store["key.pkl"] = {"x": 42}

    actual = store["key.pkl"]
    assert actual == {"x": 42}


def test_transform_mapping_contains_does_not_deserialise() -> None:
    """__contains__ resolves without calling __getitem__ or the load callable.

    This is the critical correctness guarantee: a load callable that parses a
    large file must not run just to check key existence.
    """
    load_calls: list[str] = []

    def counting_load(raw: bytes) -> object:
        load_calls.append("load")
        return pickle.loads(raw)  # noqa: S301

    backend = _mem()
    backend["k.pkl"] = pickle.dumps("value")
    store = TransformMapping(
        mapping=backend,
        save=pickle.dumps,
        load=counting_load,
    )

    _ = "k.pkl" in store

    assert load_calls == [], "load callable must not be invoked by __contains__"


def test_transform_mapping_pipe_combines_mapping_and_transform() -> None:
    """| combines a backend wrapper with a recorder transform into a usable store."""
    store = TransformMapping(mapping=_mem()) | _make_recorder_transform(
        _default_recorder()
    )

    store["k.pkl"] = [1, 2, 3]

    assert store["k.pkl"] == [1, 2, 3]


def test_transform_mapping_missing_key_raises() -> None:
    """Reading an absent key raises KeyError (propagated from the inner mapping)."""
    store = TransformMapping(mapping=_mem()) | _make_recorder_transform(
        _default_recorder()
    )

    with pytest.raises(KeyError):
        _ = store["missing.pkl"]


def test_transform_mapping_raises_when_both_sides_have_a_mapping() -> None:
    """Merging two TransformMappings that both carry a backend raises TypeError.

    The | operator is designed to merge a mapping-bearing instance with a
    save/load-only instance. When both sides have a mapping, one would be
    silently dropped, so the error is raised explicitly instead.
    """
    with pytest.raises(TypeError, match="both carry a backend mapping"):
        TransformMapping(mapping=_mem()) | TransformMapping(mapping=_mem())


# ---------------------------------------------------------------------------
# PrefixedMapping
# ---------------------------------------------------------------------------


def test_prefixed_mapping_stores_with_prefix() -> None:
    """Keys are stored under the prefixed form in the inner mapping."""
    inner: dict[str, bytes] = {}
    m = PrefixedMapping(inner, prefix="ns:")

    m["key"] = b"val"

    assert "ns:key" in inner
    assert "key" not in inner


def test_prefixed_mapping_retrieves_without_prefix() -> None:
    """Values stored under a prefixed key are retrievable via the bare key."""
    inner: dict[str, bytes] = {"ns:key": b"val"}
    m = PrefixedMapping(inner, prefix="ns:")

    assert m["key"] == b"val"


def test_prefixed_mapping_contains_checks_prefixed_key() -> None:
    """__contains__ looks up the prefixed form in the inner mapping."""
    inner: dict[str, bytes] = {"ns:key": b"val"}
    m = PrefixedMapping(inner, prefix="ns:")

    assert "key" in m
    assert "ns:key" not in m


def test_prefixed_mapping_iter_strips_prefix() -> None:
    """__iter__ yields bare keys, stripping the prefix."""
    inner: dict[str, bytes] = {"ns:a": b"1", "ns:b": b"2", "other:c": b"3"}
    m = PrefixedMapping(inner, prefix="ns:")

    assert set(m) == {"a", "b"}


def test_prefixed_mapping_delete_removes_prefixed_key() -> None:
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
        pass

    assert inner.entered is True
    assert inner.exited is True


def test_prefixed_mapping_does_not_fail_when_inner_has_no_context_manager() -> None:
    """__enter__/__exit__ on a plain dict inner store does not raise."""
    m = PrefixedMapping({}, prefix="p:")

    with m:
        m["k"] = b"v"

    assert m["k"] == b"v"


def test_routes_io_through_entered_proxy_when_inner_enter_returns_different_object() -> None:
    """Writes and reads after entry go through the object returned by __enter__."""

    class ProxyStore(MutableMapping[str, bytes]):
        """A store whose __enter__ returns a separate proxy dict, not self."""

        def __init__(self) -> None:
            self.proxy: dict[str, bytes] = {}

        def __enter__(self) -> dict[str, bytes]:  # type: ignore[override]
            return self.proxy

        def __exit__(self, *_: object) -> None:
            pass

        def __getitem__(self, k: str) -> bytes:
            raise KeyError(k)

        def __setitem__(self, k: str, v: bytes) -> None:
            pass

        def __delitem__(self, k: str) -> None:
            pass

        def __iter__(self) -> Iterator[str]:
            return iter([])

        def __len__(self) -> int:
            return 0

    inner = ProxyStore()
    m = PrefixedMapping(inner, prefix="p:")

    with m as entered_m:
        entered_m["key"] = b"val"
        actual = entered_m["key"]

    assert actual == b"val"
