from ditto._version import __version__ as version
from ditto.snapshot import Snapshot
from ditto._unittest import DittoTestCase
from ditto.io._plugins import MARK_REGISTRY

# Base mark and convenience marks — accessible as @ditto.record, @ditto.yaml, etc.
from ._marks import record
from ._marks import yaml, json, pickle


__all__ = (
    "version",
    "Snapshot",
    "DittoTestCase",
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
    if name in MARK_REGISTRY:
        return MARK_REGISTRY[name]
    raise AttributeError(f"module 'ditto' has no attribute {name!r}")
