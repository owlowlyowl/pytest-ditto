import importlib.metadata
import warnings
from collections.abc import Iterable, Iterator, MutableMapping
from importlib.metadata import EntryPoint

from ._contract import (
    ContractProblem,
    Registration,
    find_identifier_problems,
    find_legacy_problems,
    find_name_problems,
)
from ._protocol import Recorder
from ..exceptions import (
    DittoRecorderConflictError,
    DittoRecorderLoadError,
    DittoWarning,
)


__all__ = (
    "RECORDER_REGISTRY",
    "RecorderRegistry",
    "load_recorders",
)


class RecorderRegistry(MutableMapping[str, Recorder]):
    """
    Recorders keyed by name, imported only when first looked up.

    Names come from `ditto_recorders` entry-point metadata, which needs no
    import, so membership tests and iteration never import a plugin. Recorders
    added with `registry[name] = recorder` take precedence over entry points.
    Iteration preserves discovery order, followed by additional assigned names
    in insertion order. Loading or overriding a recorder does not move its name.

    Registrations that break the plugin contract are listed in `problems`, found
    from metadata alone. Looking up a name a problem affects raises
    `DittoRecorderConflictError` rather than picking one registration.
    Assigning a recorder to that name resolves it. When a plugin recorder loads,
    its identifier is checked against the other loaded plugin recorders'.

    Looking up values (including through `get`, `items`, `values`, or `pop`)
    can load plugins and raise `DittoRecorderLoadError` or
    `DittoRecorderConflictError`. Assignment, `del`, and `clear` never load
    plugins. Pytest's `monkeypatch.setitem` and `delitem` first read the old
    value for restoration, so they also load an existing entry point and fail if
    it is broken or conflicted.

    Parameters
    ----------
    entry_points : Iterable[EntryPoint], optional
        Entry points to serve. Defaults to the installed `ditto_recorders` group.
    marks_entry_points : Iterable[EntryPoint], optional
        Entry points in the removed `ditto_marks` group, which identify plugins
        still on the 1.x contract. Defaults to the installed `ditto_marks` group.
    """

    def __init__(
        self,
        entry_points: Iterable[EntryPoint] | None = None,
        marks_entry_points: Iterable[EntryPoint] | None = None,
    ) -> None:
        if entry_points is None:
            entry_points = importlib.metadata.entry_points(group="ditto_recorders")
        if marks_entry_points is None:
            marks_entry_points = importlib.metadata.entry_points(group="ditto_marks")
        entry_points = list(entry_points)
        legacy = {_distribution(ep) for ep in marks_entry_points}

        self._entries: dict[str, Recorder | EntryPoint] = {}
        for ep in entry_points:
            self._entries.setdefault(ep.name, ep)
        self._legacy_distributions = frozenset(d.partition(" ")[0] for d in legacy)
        self._problems = (
            *find_name_problems(
                Registration(ep.name, _distribution(ep)) for ep in entry_points
            ),
            *find_legacy_problems(legacy),
        )
        self._conflicts = {
            name: problem for problem in self._problems for name in problem.names
        }
        # Plugin recorders loaded so far, and their distributions, for the
        # identifier check.
        self._loaded: dict[str, str] = {}

    @property
    def problems(self) -> tuple[ContractProblem, ...]:
        """The registrations that break the plugin contract, found from metadata."""
        return self._problems

    def __getitem__(self, name: str) -> Recorder:
        if name in self._conflicts:
            raise DittoRecorderConflictError(self._conflicts[name].message)
        entry = self._entries[name]
        if isinstance(entry, EntryPoint):
            distribution = _distribution(entry)
            try:
                recorder = entry.load()
                if not isinstance(recorder, Recorder):
                    raise TypeError(
                        f"{entry.value} is a {type(recorder).__name__}, "
                        "not a ditto.recorders.Recorder"
                    )
            except Exception as exc:
                raise DittoRecorderLoadError(
                    name, distribution, exc, self._upgrade_hint(entry)
                ) from exc
            self._check_identifier(Registration(name, distribution), recorder)
            self._entries[name] = entry = recorder
            self._loaded[name] = distribution
        return entry

    def __setitem__(self, name: str, recorder: Recorder) -> None:
        self._entries[name] = recorder
        self._conflicts.pop(name, None)
        self._loaded.pop(name, None)

    def __delitem__(self, name: str) -> None:
        del self._entries[name]
        self._conflicts.pop(name, None)
        self._loaded.pop(name, None)

    def __contains__(self, name: object) -> bool:
        return name in self._entries

    def __iter__(self) -> Iterator[str]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __copy__(self) -> "RecorderRegistry":
        """Copy registrations and cached values without loading entry points."""
        registry = RecorderRegistry([], [])
        registry._entries = self._entries.copy()
        registry._legacy_distributions = self._legacy_distributions
        registry._problems = self._problems
        registry._conflicts = self._conflicts.copy()
        registry._loaded = self._loaded.copy()
        return registry

    def clear(self) -> None:
        """Remove all registrations without loading any entry points."""
        self._entries.clear()
        self._conflicts.clear()
        self._loaded.clear()

    def _check_identifier(self, registration: Registration, recorder: Recorder) -> None:
        """Raise if `recorder` shares its identifier with another loaded plugin."""
        others = [
            (Registration(name, distribution), loaded.identifier)
            for name, distribution in self._loaded.items()
            if isinstance(loaded := self._entries[name], Recorder)
            and loaded is not recorder
        ]
        problems = find_identifier_problems([
            *others,
            (registration, recorder.identifier),
        ])
        if problems:
            raise DittoRecorderConflictError(problems[0].message)

    def _upgrade_hint(self, entry: EntryPoint) -> str:
        if entry.dist is None or entry.dist.name not in self._legacy_distributions:
            return ""
        return (
            f"{entry.dist.name} uses the 1.x plugin contract; install "
            f"{entry.dist.name}>=2.0."
        )


def _distribution(entry: EntryPoint) -> str:
    """Return the name and version of the distribution registering `entry`."""
    if entry.dist is None:
        return "an unknown distribution"
    return f"{entry.dist.name} {entry.dist.version}"


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


RECORDER_REGISTRY: RecorderRegistry = RecorderRegistry()
