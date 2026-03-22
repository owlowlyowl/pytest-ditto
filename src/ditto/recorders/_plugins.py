import importlib.metadata
import warnings

from ._protocol import Recorder


__all__ = ("RECORDER_REGISTRY", "MARK_REGISTRY", "load_recorders", "load_mark_plugins")


def load_recorders() -> dict[str, Recorder]:
    """
    Discover and return all registered recorders.

    Loads recorders from the `ditto_recorders` entry point group. Each entry
    point value must be a `Recorder` instance.

    Broken entry points are skipped with a warning rather than crashing.

    Returns
    -------
    dict[str, Recorder]
        Mapping of entry point name to recorder instance.
    """
    result: dict[str, Recorder] = {}
    for ep in importlib.metadata.entry_points(group="ditto_recorders"):
        try:
            result[ep.name] = ep.load()
        except Exception as exc:
            warnings.warn(
                f"ditto: failed to load recorder {ep.name!r}: {exc}",
                stacklevel=2,
            )
    return result


def load_mark_plugins() -> dict[str, object]:
    """
    Discover and return all registered marks.

    Loads marks from the `ditto_marks` entry point group. Each entry point
    value must be a callable that returns a marks object.

    Broken entry points are skipped with a warning rather than crashing.

    Returns
    -------
    dict[str, object]
        Mapping of entry point name to mark object.
    """
    result: dict[str, object] = {}
    for ep in importlib.metadata.entry_points(group="ditto_marks"):
        try:
            result[ep.name] = ep.load()()
        except Exception as exc:
            warnings.warn(
                f"ditto: failed to load mark plugin {ep.name!r}: {exc}",
                stacklevel=2,
            )
    return result


RECORDER_REGISTRY: dict[str, Recorder] = load_recorders()
MARK_REGISTRY: dict[str, object] = load_mark_plugins()
