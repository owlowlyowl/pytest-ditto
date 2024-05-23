import pkg_resources


io_registry = {}


def load_plugins():
    for entry_point in pkg_resources.iter_entry_points('ditto'):
        plugin_class = entry_point.load()
        print("loading plugins", plugin_class)
        io_registry[plugin_class.__name__] = plugin_class


# Load plugins when the module is imported
load_plugins()
