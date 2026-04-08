from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from pathlib import Path


__all__ = ("LocalMapping",)


class LocalMapping(MutableMapping[str, bytes]):
    """MutableMapping backed by a local filesystem directory.

    Keys map directly to filenames within `root`. Uses pathlib operations
    so filenames with special characters (brackets, etc.) are handled as
    literals, not glob patterns.

    Replaces `fsspec.get_mapper(local_path)` for the default `.ditto/`
    backend to avoid fsspec treating bracket-containing test names as globs.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        # .root attribute mirrors fsspec FSMap for compatibility
        self.root = str(root)

    def _path(self, key: str) -> Path:
        return self._root / key

    def __getitem__(self, key: str) -> bytes:
        p = self._path(key)
        try:
            return p.read_bytes()
        except FileNotFoundError:
            raise KeyError(key)

    def __setitem__(self, key: str, value: bytes) -> None:
        p = self._path(key)
        self._root.mkdir(parents=True, exist_ok=True)
        p.write_bytes(value)

    def __delitem__(self, key: str) -> None:
        p = self._path(key)
        try:
            p.unlink()
        except FileNotFoundError:
            raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return self._path(key).is_file()

    def __iter__(self) -> Iterator[str]:
        if not self._root.is_dir():
            return iter([])
        return (f.name for f in self._root.iterdir() if f.is_file())

    def __len__(self) -> int:
        return sum(1 for _ in self)
