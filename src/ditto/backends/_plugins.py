from __future__ import annotations

import importlib.metadata
import warnings
from collections.abc import Callable, MutableMapping


__all__ = ("BACKEND_REGISTRY", "load_backends")


BACKEND_REGISTRY: dict[str, Callable[..., MutableMapping[str, bytes]]] = {}


def load_backends() -> None:
    """Load URI-scheme backend factories from the `ditto_backends` entry-point group.

    Notes
    -----
    Each entry point must resolve to a callable with the signature
    `factory(uri: str, **storage_options) -> MutableMapping[str, bytes]`.

    The entry point name is the URI scheme handled by that factory, for example
    `redis`, `postgresql`, or `duckdb`.
    """
    for ep in importlib.metadata.entry_points(group="ditto_backends"):
        try:
            BACKEND_REGISTRY[ep.name] = ep.load()
        except Exception:
            warnings.warn(
                f"Failed to load ditto backend {ep.name!r}; it will be unavailable.",
                stacklevel=1,
            )
