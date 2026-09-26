import importlib.metadata
import warnings
from collections.abc import Iterable, Iterator, MutableMapping
from importlib.metadata import EntryPoint

from ._protocol import Recorder
from ..exceptions import DittoRecorderLoadError, DittoWarning


__all__ = (
    "RECORDER_REGISTRY",
    "MARK_REGISTRY",
    "RecorderRegistry",
    "load_recorders",
    "load_mark_plugins",
)


class RecorderRegistry(MutableMapping[str, Recorder]):
    """
    Recorders keyed by name, imported only when first looked up.

    Names come from `ditto_recorders` entry-point metadata, which needs no
    import, so membership tests and iteration never import a plugin. Recorders
    added with `registry[name] = recorder` take precedence over entry points.
    Iteration preserves discovery order, followed by additional assigned names
    in insertion order. Loading or overriding a recorder does not move its name.

    Looking up values (including through `get`, `items`, `values`, or `pop`)
    can load plugins and raise `DittoRecorderLoadError`. Assignment, `del`, and
    `clear` never load plugins. Pytest's `monkeypatch.setitem` and `delitem`
    first read the old value for restoration, so they also load an existing
    entry point and fail if it is broken.

    Parameters
    ----------
    entry_points : Iterable[EntryPoint], optional
        Entry points to serve. Defaults to the installed `ditto_recorders` group.
    """

    def __init__(self, entry_points: Iterable[EntryPoint] | None = None) -> None:
        if entry_points is None:
            entry_points = importlib.metadata.entry_points(group="ditto_recorders")
        self._entry_points: dict[str, EntryPoint] = {ep.name: ep for ep in entry_points}
        self._recorders: dict[str, Recorder] = {}

    def __getitem__(self, name: str) -> Recorder:
        if name in self._recorders:
            return self._recorders[name]
        ep = self._entry_points[name]
        try:
            recorder = ep.load()
        except Exception as exc:
            dist = ep.dist.name if ep.dist else "an unknown distribution"
            raise DittoRecorderLoadError(name, dist, exc) from exc
        self._recorders[name] = recorder
        return recorder

    def __setitem__(self, name: str, recorder: Recorder) -> None:
        self._recorders[name] = recorder

    def __delitem__(self, name: str) -> None:
        if name not in self:
            raise KeyError(name)
        self._recorders.pop(name, None)
        self._entry_points.pop(name, None)

    def __contains__(self, name: object) -> bool:
        return name in self._recorders or name in self._entry_points

    def __iter__(self) -> Iterator[str]:
        yield from self._entry_points
        for name in self._recorders:
            if name not in self._entry_points:
                yield name

    def __len__(self) -> int:
        return len(self._entry_points) + sum(
            name not in self._entry_points for name in self._recorders
        )

    def clear(self) -> None:
        """Remove all registrations without loading any entry points."""
        self._recorders.clear()
        self._entry_points.clear()


def load_recorders() -> dict[str, Recorder]:
    """
    Discover and return all registered recorders.

    Loads recorders from the `ditto_recorders` entry point group. Each entry
    point value must be a `Recorder` instance.

    Broken entry points are skipped with a warning rather than crashing.

    Returns
    -------
    dict[str, Recorder]
        Mapping of entry point name to recorder instance.
    """
    result: dict[str, Recorder] = {}
    for ep in importlib.metadata.entry_points(group="ditto_recorders"):
        try:
            result[ep.name] = ep.load()
        except Exception as exc:
            warnings.warn(
                f"ditto: failed to load recorder {ep.name!r}: {exc}",
                category=DittoWarning,
                stacklevel=2,
            )
    return result


def load_mark_plugins() -> dict[str, object]:
    """
    Discover and return all registered marks.

    Loads marks from the `ditto_marks` entry point group. Each entry point
    value must be a callable that returns a marks object.

    Broken entry points are skipped with a warning rather than crashing.

    Returns
    -------
    dict[str, object]
        Mapping of entry point name to mark object.
    """
    result: dict[str, object] = {}
    for ep in importlib.metadata.entry_points(group="ditto_marks"):
        try:
            result[ep.name] = ep.load()()
        except Exception as exc:
            warnings.warn(
                f"ditto: failed to load mark plugin {ep.name!r}: {exc}",
                category=DittoWarning,
                stacklevel=2,
            )
    return result


RECORDER_REGISTRY: RecorderRegistry = RecorderRegistry()
MARK_REGISTRY: dict[str, object] = load_mark_plugins()
