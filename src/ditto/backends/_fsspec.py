from __future__ import annotations

import posixpath
from collections.abc import Iterator, Mapping, MutableMapping
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from fsspec.implementations.local import LocalFileSystem

from ditto._atomic import is_temp_name, write_atomically

if TYPE_CHECKING:
    from fsspec import AbstractFileSystem


__all__ = ("FsspecMapping",)


def _info_mtime(info: Mapping[str, object]) -> float | None:
    """Extract a POSIX mtime from an fsspec info dict, or None if absent.

    Local fs reports `mtime` (float); S3 reports `LastModified` (datetime); GCS
    `last_modified`. Anything else (memory fs) has no mtime.
    """
    match info.get("mtime", info.get("LastModified", info.get("last_modified"))):
        case bool():  # bool is an int subclass — never a timestamp
            return None
        case int() | float() as ts:
            return float(ts)
        case datetime() as dt:
            return dt.timestamp()
        case _:
            return None


def _is_leftover_temp(path: str) -> bool:
    """True for a temporary file an interrupted atomic write left behind.

    It isn't a snapshot, so the mapping never lists it.
    """
    return is_temp_name(posixpath.basename(path))


class FsspecMapping(MutableMapping[str, bytes]):
    """MutableMapping backed by any fsspec AbstractFileSystem.

    Uses `fs.find()` for iteration and direct `fs.open` / `fs.rm` /
    `fs.isfile` for individual key access — never `fs.glob()`. This
    avoids fsspec's `fnmatch`-based glob expansion, which silently drops
    keys whose names contain bracket characters (e.g. parametrised test
    names like `test_foo[bar]`).

    Works with any fsspec backend: local, S3 (`s3fs`), GCS
    (`gcsfs`), Azure (`adlfs`), in-memory, etc.

    Parameters
    ----------
    fs : AbstractFileSystem
        An initialised `fsspec.AbstractFileSystem` instance.
    root : str
        Root path within the filesystem (e.g. `"s3://my-bucket/ditto"`).
    """

    def __init__(self, fs: AbstractFileSystem, root: str) -> None:
        self._fs = fs
        self._root = root.rstrip("/")
        # .root mirrors the attribute LocalMapping exposed for fsspec compatibility;
        # plugin.py's _get_root() uses it to register this backend's root directory
        # so ghost-detection (Pass 2) doesn't flag its own .ditto/ as unused.
        self.root = self._root

    def _full_path(self, key: str) -> str:
        if posixpath.isabs(key):
            raise ValueError(f"key {key!r} must be a relative path, not absolute")
        candidate = posixpath.normpath(f"{self._root}/{key}")
        # Candidate must be strictly inside the root, not equal to it —
        # a key that resolves to the root directory itself (e.g. ".") is invalid.
        if not candidate.startswith(self._root + "/"):
            raise ValueError(
                f"key {key!r} would escape the snapshot root {self._root!r}"
            )
        return candidate

    def __getitem__(self, key: str) -> bytes:
        p = self._full_path(key)
        try:
            with self._fs.open(p, "rb") as f:
                return f.read()  # type: ignore[return-value]  # fsspec binary mode
        except FileNotFoundError:
            raise KeyError(key)

    def __setitem__(self, key: str, value: bytes) -> None:
        """Store `value` under `key`, replacing any previous value whole.

        On the local filesystem, opening the destination for writing would
        truncate it before any new bytes arrive, so the value is written
        atomically instead: a failed write leaves the previous value intact.
        Object stores (S3, GCS, Azure) already replace an object whole.
        """
        p = self._full_path(key)
        parent = posixpath.dirname(p)
        self._fs.makedirs(parent, exist_ok=True)
        if isinstance(self._fs, LocalFileSystem):
            write_atomically(Path(p), value)
            return
        with self._fs.open(p, "wb") as f:
            f.write(value)  # type: ignore[arg-type]  # fsspec binary mode

    def __delitem__(self, key: str) -> None:
        p = self._full_path(key)
        if not self._fs.isfile(p):
            raise KeyError(key)
        self._fs.rm(p)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return self._fs.isfile(self._full_path(key))

    def __iter__(self) -> Iterator[str]:
        if not self._fs.exists(self._root):
            return iter([])
        prefix = self._root + "/"
        return (
            p[len(prefix) :]
            for p in self._fs.find(self._root, detail=False)
            if p.startswith(prefix) and not _is_leftover_temp(p)
        )

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def stat_entries(self) -> Iterator[tuple[str, int, float | None]]:
        """Yield (key, size_bytes, modified) for each stored snapshot.

        Uses one `fs.find(detail=True)` listing, so size and mtime come from a
        single round trip — no per-key reads. `modified` is None when the
        filesystem reports no mtime. Mirrors `__iter__`'s root-prefix stripping.
        """
        if not self._fs.exists(self._root):
            return
        prefix = self._root + "/"
        entries: dict[str, dict[str, object]] = self._fs.find(self._root, detail=True)  # type: ignore[assignment]
        for path, info in entries.items():
            if not path.startswith(prefix) or _is_leftover_temp(path):
                continue
            yield path[len(prefix) :], int(info.get("size") or 0), _info_mtime(info)  # type: ignore[arg-type]
