from __future__ import annotations

import importlib.metadata
import warnings
from collections.abc import Callable, MutableMapping


__all__ = ("BACKEND_REGISTRY", "load_backends")


BACKEND_REGISTRY: dict[str, Callable[[], MutableMapping[str, bytes]]] = {}


def load_backends() -> None:
    """Load named backends from the 'ditto_backends' entry-point group."""
    for ep in importlib.metadata.entry_points(group="ditto_backends"):
        try:
            BACKEND_REGISTRY[ep.name] = ep.load()
        except Exception:
            warnings.warn(
                f"Failed to load ditto backend {ep.name!r}; it will be unavailable.",
                stacklevel=1,
            )
