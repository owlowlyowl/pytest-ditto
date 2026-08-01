from collections.abc import Mapping
from typing import Final, cast

from ditto.exceptions import DittoUnknownRecorderError

from ._protocol import Recorder
from ._json import json as _default
from ._plugins import (
    RECORDER_REGISTRY,
    MARK_REGISTRY,
    load_recorders,
    load_mark_plugins,
)


__all__ = (
    "Recorder",
    "RECORDER_REGISTRY",
    "MARK_REGISTRY",
    "load_recorders",
    "load_mark_plugins",
    "register",
    "get",
    "default",
)


def register(name: str, recorder: Recorder, registry: dict = RECORDER_REGISTRY) -> None:
    """
    Add or replace a recorder in the given registry.

    Parameters
    ----------
    name : str
        Key under which the recorder is registered.
    recorder : Recorder
        The recorder instance to register.
    registry : dict, optional
        Registry to mutate. Defaults to the shared `RECORDER_REGISTRY`.
        Pass an isolated dict in tests to avoid mutating shared state.
    """
    registry[name] = recorder


_MISSING: Final = object()


def get(
    name: str,
    registry: Mapping[str, Recorder] = RECORDER_REGISTRY,
    fallback: Recorder | object = _MISSING,
) -> Recorder:
    """
    Look up a recorder by name.

    Parameters
    ----------
    name : str
        Key to look up in the registry.
    registry : Mapping[str, Recorder], optional
        Registry to query. Defaults to the shared `RECORDER_REGISTRY`.
        Pass an isolated dict in tests to avoid depending on shared state.
    fallback : Recorder, optional
        Recorder to return when `name` is not found. If omitted, an unknown
        recorder raises `DittoUnknownRecorderError`.

    Returns
    -------
    Recorder
        The registered recorder, or an explicitly supplied `fallback`.
    """
    if name in registry:
        return registry[name]
    if fallback is not _MISSING:
        return cast(Recorder, fallback)
    raise DittoUnknownRecorderError(name, list(registry))


def default() -> Recorder:
    """
    Return the default recorder.

    Returns
    -------
    Recorder
        The strict JSON recorder.
    """
    return _default
