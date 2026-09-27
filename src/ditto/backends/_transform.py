from __future__ import annotations

from collections.abc import Callable, Iterator, MutableMapping
from typing import Any


__all__ = ("TransformMapping",)


class TransformMapping(MutableMapping):
    """MutableMapping that serialises/deserialises values via `save`/`load` callables.

    Wraps an underlying `MutableMapping[str, bytes]` backend. Values written via
    `__setitem__` are passed through `save` (Any → bytes) before storage; values
    read via `__getitem__` are passed through `load` (bytes → Any) after retrieval.

    Examples
    --------
    Partial instances (mapping-only or save/load-only) are combined via `|`:

    ```python
    store = TransformMapping(mapping=backend) | TransformMapping(
        save=gzip.compress, load=gzip.decompress
    )
    ```
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
        self._mapping = mapping

    def __or__(self, other: "TransformMapping") -> "TransformMapping":
        if self._mapping is not None and other._mapping is not None:
            raise TypeError(
                "Cannot merge two TransformMappings that both carry a backend mapping. "
                "Use | to combine a mapping-bearing instance with a "
                "save/load-only instance."
            )
        return TransformMapping(
            save=other._save if other._save is not None else self._save,
            load=other._load if other._load is not None else self._load,
            mapping=self._mapping if self._mapping is not None else other._mapping,
        )

    def __getitem__(self, key: str) -> Any:
        if self._mapping is None:
            raise TypeError("TransformMapping has no backend; use | to attach one.")
        if self._load is None:
            raise TypeError(
                "TransformMapping has no load callable; use | to attach one."
            )
        return self._load(self._mapping[key])

    def __setitem__(self, key: str, value: Any) -> None:
        if self._mapping is None:
            raise TypeError("TransformMapping has no backend; use | to attach one.")
        if self._save is None:
            raise TypeError(
                "TransformMapping has no save callable; use | to attach one."
            )
        self._mapping[key] = self._save(value)

    def __delitem__(self, key: str) -> None:
        if self._mapping is None:
            raise TypeError("TransformMapping has no backend; use | to attach one.")
        del self._mapping[key]

    def __iter__(self) -> Iterator[str]:
        if self._mapping is None:
            raise TypeError("TransformMapping has no backend; use | to attach one.")
        return iter(self._mapping)

    def __len__(self) -> int:
        if self._mapping is None:
            raise TypeError("TransformMapping has no backend; use | to attach one.")
        return len(self._mapping)

    def __contains__(self, key: object) -> bool:
        if self._mapping is None:
            raise TypeError("TransformMapping has no backend; use | to attach one.")
        # Delegate to the underlying mapping — never calls __getitem__/load.
        return key in self._mapping
