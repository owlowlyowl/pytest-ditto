import importlib.metadata


__all__ = [
    "IO_REGISTRY",
    "MARK_REGISTRY",
    "load_io_plugins",
    "load_mark_plugins",
]


def load_io_plugins() -> dict[str, type]:
    """
    Discovers and returns all IO handler classes registered under the 'ditto'
    entry point group. Returns a new dict each call — callers own the result.
    """
    return {
        ep.name: ep.load()
        for ep in importlib.metadata.entry_points(group="ditto")
    }


def load_mark_plugins() -> dict[str, object]:
    """
    Discovers and returns all mark objects registered under the 'ditto_marks'
    entry point group. Each entry point is called once to produce the mark.
    Returns a new dict each call — callers own the result.
    """
    return {
        ep.name: ep.load()()
        for ep in importlib.metadata.entry_points(group="ditto_marks")
    }


# Assigned once at import time from the return values of the loader functions.
# Treat as read-only after this point — use io.register() to add or override entries.
IO_REGISTRY: dict[str, type] = load_io_plugins()
MARK_REGISTRY: dict[str, object] = load_mark_plugins()
