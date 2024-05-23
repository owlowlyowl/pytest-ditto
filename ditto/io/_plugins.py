import pkg_resources


__all__ = [
    "IO_REGISTRY",
]


# Internal and third party ditto IO class plugins.
IO_REGISTRY = {}


def _load_plugins():
    for entry_point in pkg_resources.iter_entry_points('ditto'):
        plugin_class = entry_point.load()
        print("loading plugins", plugin_class)
        print(entry_point.__dict__)
        IO_REGISTRY[entry_point.name] = plugin_class


# Load plugins when the module is imported.
_load_plugins()
