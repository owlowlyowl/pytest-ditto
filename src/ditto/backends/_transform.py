from __future__ import annotations

import tempfile
from collections.abc import Callable, Iterator, MutableMapping
from pathlib import Path
from typing import Any

from ditto.recorders._protocol import Recorder


__all__ = ("TransformMapping", "_make_recorder_transform")


class TransformMapping(MutableMapping):
    """MutableMapping that serialises/deserialises values via save/load callables.

    Wraps an underlying MutableMapping[str, bytes] backend. Values written via
    __setitem__ are passed through _save (Any → bytes) before storage; values
    read via __getitem__ are passed through _load (bytes → Any) after retrieval.

    Use the | operator to combine a bare mapping wrapper with a recorder transform:

        store = TransformMapping(mapping=backend) | _make_recorder_transform(recorder)
    """

    def __init__(
        self,
        *,
        save: Callable[[Any], bytes] | None = None,
        load: Callable[[bytes], Any] | None = None,
        mapping: MutableMapping[str, bytes] | None = None,
    ) -> None:
        self._save = save
        self._load = load
        self._cache = mapping

    def __or__(self, other: "TransformMapping") -> "TransformMapping":
        return TransformMapping(
            save=other._save if other._save is not None else self._save,
            load=other._load if other._load is not None else self._load,
            mapping=self._cache if self._cache is not None else other._cache,
        )

    def __getitem__(self, key: str) -> Any:
        raw = self._cache[key]
        return self._load(raw)

    def __setitem__(self, key: str, value: Any) -> None:
        self._cache[key] = self._save(value)

    def __delitem__(self, key: str) -> None:
        del self._cache[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._cache)

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, key: object) -> bool:
        # Delegate to the underlying cache — never calls __getitem__/load.
        return key in self._cache


def _make_recorder_transform(recorder: Recorder) -> TransformMapping:
    """Return a TransformMapping whose save/load go through a temp-file bridge.

    The Recorder protocol requires a Path argument. The bridge writes/reads a
    temporary file so any Recorder can be used with any bytes-based backend.
    """

    def _save(data: Any) -> bytes:
        with tempfile.NamedTemporaryFile(suffix=f".{recorder.extension}", delete=False) as f:
            tmp = Path(f.name)
        try:
            recorder.save(data, tmp)
            return tmp.read_bytes()
        finally:
            tmp.unlink(missing_ok=True)

    def _load(raw: bytes) -> Any:
        with tempfile.NamedTemporaryFile(suffix=f".{recorder.extension}", delete=False) as f:
            tmp = Path(f.name)
        try:
            tmp.write_bytes(raw)
            return recorder.load(tmp)
        finally:
            tmp.unlink(missing_ok=True)

    return TransformMapping(save=_save, load=_load)
