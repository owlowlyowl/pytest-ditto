"""Behavioural tests for FsspecMapping and PrefixedMapping."""

from __future__ import annotations

import errno
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator, MutableMapping

import pytest
from fsspec.implementations.local import LocalFileSystem
from fsspec.implementations.memory import MemoryFileSystem

from ditto._atomic import TEMP_PREFIX
from ditto.backends import FsspecMapping, PrefixedMapping


def _mem() -> FsspecMapping:
    """FsspecMapping backed by an in-memory filesystem with a unique root.

    MemoryFileSystem uses a class-level store, so each call uses a distinct
    root path to prevent test pollution.
    """
    return FsspecMapping(
        MemoryFileSystem(skip_instance_cache=True), f"/{uuid.uuid4().hex}"
    )


# ---------------------------------------------------------------------------
# FsspecMapping
# ---------------------------------------------------------------------------


def test_fsspec_mapping_stores_and_retrieves_bytes() -> None:
    """Bytes written under a key are returned unchanged on read."""
    m = _mem()

    m["snap.json"] = b"hello"

    assert m["snap.json"] == b"hello"


def test_fsspec_mapping_raises_key_error_for_absent_key() -> None:
    """Reading a key that was never written raises KeyError."""
    m = _mem()

    with pytest.raises(KeyError):
        _ = m["missing.json"]


def test_fsspec_mapping_contains_written_key() -> None:
    """__contains__ returns True for a key that has been written."""
    m = _mem()
    m["a.json"] = b"x"

    assert "a.json" in m


def test_fsspec_mapping_does_not_contain_absent_key() -> None:
    """__contains__ returns False for a key that has never been written."""
    m = _mem()

    assert "nope.json" not in m


def test_fsspec_mapping_deletes_key() -> None:
    """Deleting a key removes it from the mapping."""
    m = _mem()
    m["a.json"] = b"x"

    del m["a.json"]

    assert "a.json" not in m


def test_fsspec_mapping_delete_absent_key_raises() -> None:
    """Deleting a key that does not exist raises KeyError."""
    m = _mem()

    with pytest.raises(KeyError):
        del m["ghost.json"]


def test_fsspec_mapping_iter_returns_filenames() -> None:
    """__iter__ yields the filenames of all stored keys."""
    m = _mem()
    m["a.json"] = b"1"
    m["b.json"] = b"2"

    assert set(m) == {"a.json", "b.json"}


def test_fsspec_mapping_len_counts_stored_keys() -> None:
    """__len__ returns the number of stored entries."""
    m = _mem()
    m["a.json"] = b"1"
    m["b.json"] = b"2"

    assert len(m) == 2


def test_fsspec_mapping_iter_returns_empty_when_root_does_not_exist() -> None:
    """__iter__ on a non-existent root yields nothing rather than raising."""
    m = _mem()  # fresh unique root — nothing written, so root does not exist yet

    assert list(m) == []
    assert len(m) == 0


def test_fsspec_mapping_stores_and_retrieves_bracket_key() -> None:
    """Keys containing bracket characters round-trip correctly."""
    m = _mem()
    key = "test_result[second]@v.json"

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
    key = "test_result[second]@v.json"

    m[key] = b"payload"

    assert key in set(m)


def test_fsspec_mapping_stores_and_retrieves_bytes_at_nested_key_path() -> None:
    """Bytes stored under a slash-containing key are returned unchanged on read."""
    m = _mem()
    key = "tests/test_api/test_something@result.json"

    m[key] = b"nested-data"

    assert m[key] == b"nested-data"
    assert key in m


def test_fsspec_mapping_iter_yields_forward_slash_keys_for_nested_files() -> None:
    """__iter__ yields forward-slash-separated relative paths for files at any depth."""
    m = _mem()
    m["flat.json"] = b"1"
    m["sub/nested.json"] = b"2"
    m["sub/deep/leaf.json"] = b"3"

    keys = set(m)

    assert keys == {"flat.json", "sub/nested.json", "sub/deep/leaf.json"}
    assert all("\\" not in k for k in keys)


def test_fsspec_mapping_removes_entry_when_nested_key_is_deleted() -> None:
    """Deleting a nested key removes the backing entry."""
    m = _mem()
    key = "mod/group@k.json"
    m[key] = b"x"

    del m[key]

    assert key not in m


def test_fsspec_mapping_raises_when_key_contains_path_traversal() -> None:
    """A key that resolves outside the root raises ValueError."""
    m = _mem()

    with pytest.raises(ValueError, match="escape"):
        m["../../outside.json"] = b"x"


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


def _local(tmp_path) -> FsspecMapping:
    """FsspecMapping on the local filesystem, rooted in `tmp_path`."""
    return FsspecMapping(LocalFileSystem(), tmp_path.as_posix())


# Writes a baseline, then caps the process's file size so the next write fails
# partway through, as it would on a full disk, whichever code path writes it.
_WRITE_PAST_A_FILE_SIZE_LIMIT = """
import resource, signal, sys
from fsspec.implementations.local import LocalFileSystem
from ditto.backends import FsspecMapping

m = FsspecMapping(LocalFileSystem(), sys.argv[1])
m["mod.test@k.json"] = b"old baseline"
signal.signal(signal.SIGXFSZ, signal.SIG_IGN)  # fail with EFBIG, don't die
resource.setrlimit(resource.RLIMIT_FSIZE, (4, resource.RLIM_INFINITY))
try:
    m["mod.test@k.json"] = b"a new value longer than the limit"
except OSError as exc:
    print(exc.errno)
"""


@pytest.mark.skipif(sys.platform == "win32", reason="needs RLIMIT_FSIZE")
def test_fsspec_mapping_keeps_previous_local_value_when_a_write_fails(
    tmp_path,
) -> None:
    """A local write that fails partway through leaves the previous value
    intact and no temporary file behind."""
    result = subprocess.run(
        [sys.executable, "-c", _WRITE_PAST_A_FILE_SIZE_LIMIT, tmp_path.as_posix()],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == str(errno.EFBIG)
    assert _local(tmp_path)["mod.test@k.json"] == b"old baseline"
    assert [p.name for p in tmp_path.iterdir()] == ["mod.test@k.json"]


def test_fsspec_mapping_keeps_previous_local_value_when_the_replace_fails(
    tmp_path, monkeypatch
) -> None:
    """A local write whose final rename fails leaves the previous value intact."""
    m = _local(tmp_path)
    m["mod.test@k.json"] = b"old"

    def failing_replace(src, dst):
        raise OSError("rename failed")

    monkeypatch.setattr("ditto._atomic.os.replace", failing_replace)
    with pytest.raises(OSError):
        m["mod.test@k.json"] = b"new"

    monkeypatch.undo()
    assert m["mod.test@k.json"] == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["mod.test@k.json"]


def test_fsspec_mapping_does_not_list_a_leftover_temporary_file(tmp_path) -> None:
    """A temporary file an interrupted write left behind isn't a snapshot."""
    m = _local(tmp_path)
    m["mod.test@k.json"] = b"x"
    (tmp_path / f"{TEMP_PREFIX}0123abcd.tmp").write_bytes(b"partial")

    assert list(m) == ["mod.test@k.json"]
    assert [key for key, _, _ in m.stat_entries()] == ["mod.test@k.json"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_fsspec_mapping_creates_local_files_with_default_permissions(
    tmp_path,
) -> None:
    """An atomically written snapshot gets the permissions `open` would give
    it, not the owner-only mode of a secure temporary file."""
    umask = os.umask(0o022)
    try:
        _local(tmp_path)["mod.test@k.json"] = b"x"
    finally:
        os.umask(umask)

    assert (tmp_path / "mod.test@k.json").stat().st_mode & 0o777 == 0o644


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


class _SuppressingStore(dict[str, bytes]):
    """A dict store whose __exit__ records the exception and returns `suppress`."""

    def __init__(self, *, suppress: bool) -> None:
        super().__init__()
        self.suppress = suppress
        self.exit_args: tuple[object, ...] | None = None

    def __enter__(self) -> "_SuppressingStore":
        return self

    def __exit__(self, *args: object) -> bool:
        self.exit_args = args
        return self.suppress


def test_prefixed_mapping_suppresses_exception_when_inner_exit_suppresses() -> None:
    """An exception raised in the with-block is suppressed when the inner store's
    __exit__ returns True, as the context-manager protocol requires."""
    inner = _SuppressingStore(suppress=True)
    error = ValueError("boom")

    with PrefixedMapping(inner, prefix="p:"):
        raise error

    assert inner.exit_args is not None
    assert inner.exit_args[:2] == (ValueError, error)


def test_prefixed_mapping_propagates_exception_when_inner_exit_does_not_suppress() -> (
    None
):
    """An exception raised in the with-block propagates when the inner store's
    __exit__ returns a falsy value."""
    inner = _SuppressingStore(suppress=False)

    with pytest.raises(ValueError, match="boom"):
        with PrefixedMapping(inner, prefix="p:"):
            raise ValueError("boom")


def test_prefixed_mapping_propagates_exception_when_inner_has_no_context_manager() -> (
    None
):
    """With a plain dict inner store there is nothing to suppress, so the exception
    propagates."""
    with pytest.raises(ValueError, match="boom"):
        with PrefixedMapping({}, prefix="p:"):
            raise ValueError("boom")


def test_prefixed_mapping_does_not_fail_when_inner_has_no_context_manager() -> None:
    """__enter__/__exit__ on a plain dict inner store does not raise."""
    m = PrefixedMapping({}, prefix="p:")

    with m:
        m["k"] = b"v"

    assert m["k"] == b"v"


def test_routes_io_through_entered_proxy_when_inner_returns_proxy() -> None:
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


# ── FsspecMapping.stat_entries ─────────────────────────────────────────────────


def test_stat_entries_reports_size_and_mtime_for_local_files(tmp_path) -> None:
    """stat_entries yields each key with its byte size and a real mtime on local fs."""
    backend = FsspecMapping(LocalFileSystem(), str(tmp_path / "snaps"))
    backend["mod.test_a@v.json"] = b"hello"

    by_key = {k: (size, mtime) for k, size, mtime in backend.stat_entries()}

    assert by_key["mod.test_a@v.json"][0] == 5
    assert by_key["mod.test_a@v.json"][1] is not None


def test_stat_entries_is_empty_when_root_is_absent(tmp_path) -> None:
    """stat_entries yields nothing when the backend root does not exist."""
    backend = FsspecMapping(LocalFileSystem(), str(tmp_path / "missing"))

    assert list(backend.stat_entries()) == []


def test_stat_entries_reports_none_mtime_when_filesystem_has_no_mtime() -> None:
    """A filesystem that reports no mtime yields modified=None alongside the size."""
    backend = _mem()
    backend["mod.test_a@v.json"] = b"hi"

    (entry,) = backend.stat_entries()

    assert (entry[1], entry[2]) == (2, None)
