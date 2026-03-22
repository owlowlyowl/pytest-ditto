from ditto._version import __version__ as version
from ditto.snapshot import Snapshot
from ditto._unittest import DittoTestCase
from .exceptions import DuplicateSnapshotKeyError

# Base mark and convenience marks — accessible as @ditto.record, @ditto.yaml, etc.
from ._marks import record
from ._marks import yaml, json, pickle


__all__ = (
    "version",
    "Snapshot",
    "DittoTestCase",
    "DuplicateSnapshotKeyError",
    "record",
    "yaml",
    "json",
    "pickle",
)


def __getattr__(name: str):
    """
    Resolve plugin marks (e.g. `@ditto.pandas`) on attribute access.

    Called by Python only when normal attribute lookup fails, so built-in names
    defined above are served directly. Marks registered via the `ditto_marks`
    entry point group are resolved here without being injected into the module
    namespace at import time.

    Parameters
    ----------
    name : str
        The attribute name being accessed.

    Returns
    -------
    object
        The mark object registered under `name` in MARK_REGISTRY.

    Raises
    ------
    AttributeError
        If `name` is not a registered plugin mark.
    """
    # Imported here rather than at module level so MARK_REGISTRY is never exposed
    # as a public attribute of the `ditto` namespace. The import cost is paid only
    # when an unknown attribute is accessed, and importlib caches module imports so
    # the registry is only loaded from entry points once regardless of how many
    # times __getattr__ is called.
    from .recorders._plugins import MARK_REGISTRY

    if name in MARK_REGISTRY:
        return MARK_REGISTRY[name]
    raise AttributeError(f"module 'ditto' has no attribute {name!r}")
