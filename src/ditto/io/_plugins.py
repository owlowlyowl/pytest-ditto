import importlib.metadata


__all__ = [
    "IO_REGISTRY",
    "MARK_REGISTRY",
]


# Internal and third party ditto IO class plugins.
IO_REGISTRY = {}
MARK_REGISTRY = {}


def _load_plugins():
    for entry_point in importlib.metadata.entry_points(group="ditto"):
        plugin_class = entry_point.load()
        IO_REGISTRY[entry_point.name] = plugin_class

    for entry_point in importlib.metadata.entry_points(group="ditto_marks"):
        mark_fn = entry_point.load()
        MARK_REGISTRY[entry_point.name] = mark_fn()


# Load plugins when the module is imported.
_load_plugins()
