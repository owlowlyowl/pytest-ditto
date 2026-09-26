from typing import Any

from pytest import MarkDecorator

from ditto._version import __version__ as version
from ditto.snapshot import Snapshot
from .exceptions import DuplicateSnapshotKeyError

# Base mark and convenience marks — accessible as @ditto.record, @ditto.yaml, etc.
from ._marks import record
from ._marks import yaml, json


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
    # Imported here rather than at module level so the registry is never exposed
    # as a public attribute of the `ditto` namespace.
    from .recorders import _plugins

    names = list(_plugins.RECORDER_REGISTRY)
    if name in names:
        return record(name)
    prefix = f"{name}."
    formats = [n.removeprefix(prefix) for n in names if n.startswith(prefix)]
    if formats:
        return _MarkNamespace(name, formats)
    raise AttributeError(f"module 'ditto' has no attribute {name!r}")


class _MarkNamespace:
    """
    The marks of one recorder namespace, such as `ditto.pandas`.

    Parameters
    ----------
    namespace : str
        The namespace segment shared by the recorder names.
    formats : list[str]
        The format segments registered under `namespace`.
    """

    def __init__(self, namespace: str, formats: list[str]) -> None:
        self._namespace = namespace
        self._formats = formats

    def __getattr__(self, fmt: str) -> MarkDecorator:
        if fmt in self._formats:
            return record(f"{self._namespace}.{fmt}")
        raise AttributeError(
            f"ditto.{self._namespace} has no recorder {fmt!r}; "
            f"available: {', '.join(sorted(self._formats))}"
        )

    def __dir__(self) -> list[str]:
        return sorted(self._formats)

    def __repr__(self) -> str:
        return f"<ditto marks {self._namespace}: {', '.join(sorted(self._formats))}>"
