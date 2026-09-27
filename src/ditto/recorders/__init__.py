from collections.abc import Mapping
from typing import Final, cast

from ditto.exceptions import DittoUnknownRecorderError

from ._protocol import Recorder
from ._json import json as _default
from ._plugins import RECORDER_REGISTRY, RecorderRegistry


__all__ = (
    "Recorder",
    "RECORDER_REGISTRY",
    "RecorderRegistry",
    "register",
    "get",
    "default",
)


def register(
    name: str,
    recorder: Recorder,
    registry: RecorderRegistry = RECORDER_REGISTRY,
) -> None:
    """
    Add a recorder to the given registry under a new name.

    The name is also the recorder's persisted identifier: it ends the
    recorder's snapshot filenames and is recorded in `ditto.lock`.

    Parameters
    ----------
    name : str
        Name to register the recorder under, following the recorder name
        grammar (`<format>` or `<namespace>.<format>`).
    recorder : Recorder
        The recorder instance to register.
    registry : RecorderRegistry, optional
        Registry to add to. Defaults to the shared `RECORDER_REGISTRY`.
        Pass an isolated `RecorderRegistry([], [])` in tests to avoid mutating
        shared state.

    Raises
    ------
    DittoRecorderConflictError
        If `name` is already registered, or breaks another naming rule together
        with the names already registered. Registered recorders cannot be
        replaced.
    """
    registry.register(name, recorder)


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
        recorder raises `DittoUnknownRecorderError`. A registered recorder that
        fails to load raises `DittoRecorderLoadError`, even if a fallback is given.

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
