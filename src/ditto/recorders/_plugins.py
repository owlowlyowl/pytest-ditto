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
from ._json import json as _default_recorder
from ._protocol import Recorder
from ..exceptions import (
    DittoRecorderConflictError,
    DittoRecorderLoadError,
    DittoWarning,
)


__all__ = (
    "CORE_DISTRIBUTION",
    "RECORDER_REGISTRY",
    "RecorderRegistry",
    "load_recorders",
)


CORE_DISTRIBUTION = "pytest-ditto"

# The recorder unmarked tests use. It is always in use, whether or not a test
# looks it up by name, so identifier checks always compare against it.
_DEFAULT = Registration("json", f"{CORE_DISTRIBUTION} (default recorder)")


class RecorderRegistry(MutableMapping[str, Recorder]):
    """
    Recorders keyed by name, imported only when first looked up.

    Names come from `ditto_recorders` entry-point metadata, which needs no
    import, so membership tests and iteration never import a plugin. Recorders
    added with `registry[name] = recorder` take precedence over entry points.
    Iteration preserves discovery order, followed by additional assigned names
    in insertion order. Loading or overriding a recorder does not move its name.

    Registrations that break the plugin contract are listed in `problems`.
    Naming problems are found from metadata alone. An identifier collision is
    found when a recorder loads with the identifier of a loaded recorder or of
    the default JSON recorder; from then on it is listed too. Looking up any
    name a problem affects raises `DittoRecorderConflictError`, so the registry
    never picks one of the conflicting registrations. Core's own recorders are
    never disabled by a plugin's collision with them. Assigning or deleting a
    name resolves its conflict, and a problem is listed while any of its names
    remains in conflict.

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
        self._core = frozenset(
            ep.name
            for ep in entry_points
            if ep.dist is not None and ep.dist.name == CORE_DISTRIBUTION
        )
        self._legacy_distributions = frozenset(d.partition(" ")[0] for d in legacy)
        self._problems = [
            *find_name_problems(
                Registration(ep.name, _distribution(ep)) for ep in entry_points
            ),
            *find_legacy_problems(legacy),
        ]
        self._conflicts = {
            name: problem for problem in self._problems for name in problem.names
        }
        # Plugin recorders loaded so far, and their distributions, for the
        # identifier check.
        self._loaded: dict[str, str] = {}

    @property
    def problems(self) -> tuple[ContractProblem, ...]:
        """The contract problems found so far that are not yet resolved.

        A problem is resolved once every name it affects has been reassigned or
        deleted. A problem affecting no names (a 1.x plugin) stays until `clear`.
        """
        return tuple(
            problem
            for problem in self._problems
            if not problem.names or not problem.names.isdisjoint(self._conflicts)
        )

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
            self._entries[name] = recorder
            self._loaded[name] = distribution
            self._check_identifier(Registration(name, distribution), recorder)
            entry = recorder
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
        registry._core = self._core
        registry._legacy_distributions = self._legacy_distributions
        registry._problems = self._problems.copy()
        registry._conflicts = self._conflicts.copy()
        registry._loaded = self._loaded.copy()
        return registry

    def clear(self) -> None:
        """Remove all registrations without loading any entry points."""
        self._entries.clear()
        self._problems.clear()
        self._conflicts.clear()
        self._loaded.clear()

    def _check_identifier(self, registration: Registration, recorder: Recorder) -> None:
        """Record and raise a collision between `recorder` and a loaded recorder.

        Recorders are compared by object, so names that alias one recorder never
        collide, and recorders already in conflict are skipped, so a collision is
        recorded once. The collision affects every name bound to a colliding
        recorder, except core's own; it is raised only if it affects
        `registration`.
        """
        clashes: dict[int, list[Registration]] = {}
        loaded = [(_DEFAULT, _default_recorder)] + [
            (Registration(name, distribution), other)
            for name, distribution in self._loaded.items()
            if name not in self._conflicts
            and isinstance(other := self._entries[name], Recorder)
        ]
        for other_registration, other in loaded:
            if other is not recorder and other.identifier == recorder.identifier:
                clashes.setdefault(id(other), []).append(other_registration)
        if not clashes:
            return

        colliding = [registration, *(names[0] for names in clashes.values())]
        (problem,) = find_identifier_problems(
            (r, recorder.identifier) for r in colliding
        )
        bound = [registration, *(r for names in clashes.values() for r in names)]
        affected = {r.name for r in bound if r is not _DEFAULT} - self._core
        self._problems.append(problem)
        for name in affected:
            self._conflicts[name] = problem
        if registration.name in affected:
            raise DittoRecorderConflictError(problem.message)

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
