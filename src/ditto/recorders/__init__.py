from collections.abc import Mapping

from ._protocol import Recorder
from ._pickle import pickle as _default
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


def get(
    name: str,
    registry: Mapping[str, Recorder] = RECORDER_REGISTRY,
    fallback: Recorder = _default,
) -> Recorder:
    """
    Look up a recorder by name, falling back to a default.

    Parameters
    ----------
    name : str
        Key to look up in the registry.
    registry : Mapping[str, Recorder], optional
        Registry to query. Defaults to the shared `RECORDER_REGISTRY`.
        Pass an isolated dict in tests to avoid depending on shared state.
    fallback : Recorder, optional
        Recorder to return when `name` is not found. Defaults to `pickle`.

    Returns
    -------
    Recorder
        The registered recorder, or `fallback` if not found.
    """
    return registry.get(name, fallback)


def default() -> Recorder:
    """
    Return the default recorder.

    Returns
    -------
    Recorder
        The pickle recorder.
    """
    return _default
