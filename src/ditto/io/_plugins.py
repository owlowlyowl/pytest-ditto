import importlib.metadata


__all__ = [
    "IO_REGISTRY",
]


# Internal and third party ditto IO class plugins.
IO_REGISTRY = {}


def _load_plugins():
    for entry_point in importlib.metadata.entry_points(group='ditto'):
        plugin_class = entry_point.load()
        IO_REGISTRY[entry_point.name] = plugin_class


# Load plugins when the module is imported.
_load_plugins()
