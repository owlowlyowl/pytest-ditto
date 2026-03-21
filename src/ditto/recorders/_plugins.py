import importlib.metadata

from ._protocol import Recorder


__all__ = ("RECORDER_REGISTRY", "MARK_REGISTRY", "load_recorders", "load_mark_plugins")


def load_recorders() -> dict[str, Recorder]:
    """
    Discover and return all registered recorders.

    Loads recorders from the `ditto_recorders` entry point group. Each entry
    point value must be a `Recorder` instance.

    Returns
    -------
    dict[str, Recorder]
        Mapping of entry point name to recorder instance.
    """
    return {
        ep.name: ep.load()
        for ep in importlib.metadata.entry_points(group="ditto_recorders")
    }


def load_mark_plugins() -> dict[str, object]:
    """
    Discover and return all registered marks.

    Loads marks from the `ditto_marks` entry point group. Each entry point
    value must be a callable that returns a marks object.

    Returns
    -------
    dict[str, object]
        Mapping of entry point name to mark object.
    """
    return {
        ep.name: ep.load()()
        for ep in importlib.metadata.entry_points(group="ditto_marks")
    }


RECORDER_REGISTRY: dict[str, Recorder] = load_recorders()
MARK_REGISTRY: dict[str, object] = load_mark_plugins()
