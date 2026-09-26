from typing import Any

from pytest import MarkDecorator

from ditto._version import __version__ as version
from ditto.snapshot import Snapshot
from .exceptions import DuplicateSnapshotKeyError

# Base mark and convenience marks — accessible as @ditto.record, @ditto.yaml, etc.
from ._marks import record
from ._marks import yaml, json
from .recorders import _plugins


__all__ = (
    "version",
    "Snapshot",
    "DuplicateSnapshotKeyError",
    "record",
    "yaml",
    "json",
)


def __getattr__(name: str) -> Any:
    """
    Resolve plugin marks (e.g. `@ditto.pandas.csv`) on attribute access.

    Called by Python only when normal attribute lookup fails, so built-in names
    defined above are served directly. Marks are derived from the names in the
    recorder registry, which come from entry-point metadata, so resolving a mark
    never imports a plugin. A bare recorder name `fmt` resolves to
    `record("fmt")`. For a dotted name `ns.fmt`, `ns` resolves to a namespace
    whose attribute `fmt` is `record("ns.fmt")`.

    Parameters
    ----------
    name : str
        The attribute name being accessed.

    Returns
    -------
    Any
        The mark for a bare recorder name, or the namespace for a dotted one.
        Annotated `Any` so plugin marks type-check without stubs.

    Raises
    ------
    AttributeError
        If `name` is neither a recorder name nor a recorder namespace.
    """
    if name in _plugins.RECORDER_REGISTRY:
        return record(name)
    if _formats_in(name):
        return _MarkNamespace(name)
    raise AttributeError(f"module 'ditto' has no attribute {name!r}")


def _formats_in(namespace: str) -> list[str]:
    """Return the formats currently registered under `namespace`, sorted."""
    prefix = f"{namespace}."
    return sorted(
        name.removeprefix(prefix)
        for name in _plugins.RECORDER_REGISTRY
        if name.startswith(prefix)
    )


class _MarkNamespace:
    """
    The marks of one recorder namespace, such as `ditto.pandas`.

    Formats are read from the recorder registry on every access, so a retained
    namespace reflects recorders registered or removed after it was created.

    Parameters
    ----------
    namespace : str
        The namespace segment shared by the recorder names.
    """

    def __init__(self, namespace: str) -> None:
        self._namespace = namespace

    def __getattr__(self, fmt: str) -> MarkDecorator:
        name = f"{self._namespace}.{fmt}"
        if name in _plugins.RECORDER_REGISTRY:
            return record(name)
        available = ", ".join(_formats_in(self._namespace)) or "none"
        raise AttributeError(
            f"ditto.{self._namespace} has no recorder {fmt!r}; available: {available}"
        )

    def __dir__(self) -> list[str]:
        return _formats_in(self._namespace)

    def __repr__(self) -> str:
        formats = ", ".join(_formats_in(self._namespace))
        return f"<ditto marks {self._namespace}: {formats}>"
