import importlib.metadata
from collections.abc import Iterable, Iterator, Mapping
from copy import copy
from importlib.metadata import EntryPoint

from ._contract import (
    ContractProblem,
    Distribution,
    Registration,
    find_legacy_problems,
    find_name_problems,
    upgrade_message,
)
from .._entry_points import LazyEntryPoints, distribution_of
from ._protocol import Recorder
from ..exceptions import DittoRecorderConflictError, DittoRecorderLoadError


__all__ = (
    "LOCAL_REGISTRATION",
    "RECORDER_REGISTRY",
    "RecorderRegistry",
)


# Stands in for a distribution in contract messages about recorders added with
# `RecorderRegistry.register`.
LOCAL_REGISTRATION = Distribution("recorders.register()", "")


class RecorderRegistry(Mapping[str, Recorder]):
    """
    Recorders keyed by name, imported only when first looked up.

    A recorder's name is also its persisted identifier: it ends the recorder's
    snapshot filenames and is recorded in `ditto.lock`.

    Names come from `ditto_recorders` entry-point metadata, which needs no
    import, so membership tests, iteration and `problems` never import a
    plugin. Every registration is checked against the plugin contract when the
    registry is built, so `problems` is complete from the start and loading a
    recorder never changes it. Looking up a name a problem affects raises
    `DittoRecorderConflictError`, so the registry never picks one of the
    conflicting registrations.

    `register` adds a recorder under a new name, and rejects a name that breaks
    the contract alone or together with the names already registered. A
    registration therefore never makes an earlier one unusable. Registrations
    are never replaced or removed. Iteration preserves discovery order, followed
    by registered names in the order they were added.

    Looking up values (including through `get`, `items` or `values`) can load
    plugins and raise `DittoRecorderLoadError` or `DittoRecorderConflictError`.

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
        legacy = {distribution_of(ep) for ep in marks_entry_points}

        self._discovered = LazyEntryPoints(entry_points, _check_recorder, self._error)
        self._registrations = list(self._discovered.registrations)
        # Recorders added with `register`.
        self._registered: dict[str, Recorder] = {}
        self._legacy_distributions = frozenset(d.name for d in legacy)
        self._problems = (
            *find_name_problems(self._registrations),
            *find_legacy_problems(legacy),
        )
        self._conflicts = {
            name: problem for problem in self._problems for name in problem.names
        }

    @property
    def problems(self) -> tuple[ContractProblem, ...]:
        """Every contract problem among the registrations, found without imports."""
        return self._problems

    def register(self, name: str, recorder: Recorder) -> None:
        """Add `recorder` under `name`, which is also its persisted identifier.

        Raises
        ------
        TypeError
            If `recorder` is not a `Recorder`.
        DittoRecorderConflictError
            If `name` is already registered, or breaks another naming rule
            together with the names already registered.
        """
        if not isinstance(recorder, Recorder):
            raise TypeError(
                f"{type(recorder).__name__} is not a ditto.recorders.Recorder"
            )
        registration = Registration(name, LOCAL_REGISTRATION)
        problems = [
            problem
            for problem in find_name_problems([*self._registrations, registration])
            if name in problem.names
        ]
        if problems:
            raise DittoRecorderConflictError(
                " ".join(problem.message for problem in problems)
            )
        self._registrations.append(registration)
        self._registered[name] = recorder

    def __getitem__(self, name: str) -> Recorder:
        if name in self._conflicts:
            raise DittoRecorderConflictError(self._conflicts[name].message)
        if name in self._registered:
            return self._registered[name]
        return self._discovered.load(name)

    def __contains__(self, name: object) -> bool:
        return name in self._discovered or name in self._registered

    def __iter__(self) -> Iterator[str]:
        yield from self._discovered
        yield from self._registered

    def __len__(self) -> int:
        return len(self._discovered) + len(self._registered)

    def __copy__(self) -> "RecorderRegistry":
        """Copy registrations and loaded recorders without loading entry points."""
        registry = RecorderRegistry([], [])
        registry._discovered = copy(self._discovered)
        registry._registrations = self._registrations.copy()
        registry._registered = self._registered.copy()
        registry._legacy_distributions = self._legacy_distributions
        registry._problems = self._problems
        registry._conflicts = self._conflicts
        return registry

    def _error(
        self, entry: EntryPoint, distribution: Distribution, exc: Exception
    ) -> DittoRecorderLoadError:
        hints = (self._upgrade_hint(distribution), _path_based_hint(exc))
        return DittoRecorderLoadError(
            entry.name, str(distribution), exc, " ".join(filter(None, hints))
        )

    def _upgrade_hint(self, distribution: Distribution) -> str:
        if distribution.name not in self._legacy_distributions:
            return ""
        return upgrade_message(distribution)


def _check_recorder(entry: EntryPoint, recorder: object) -> Recorder:
    if not isinstance(recorder, Recorder):
        raise TypeError(
            f"{entry.value} is a {type(recorder).__name__}, "
            "not a ditto.recorders.Recorder"
        )
    return recorder


def _path_based_hint(exc: Exception) -> str:
    """Explain a failure to build a `Recorder` from path-based `save`/`load`."""
    message = str(exc)
    if not (
        isinstance(exc, TypeError)
        and message.startswith("Recorder.__init__()")
        and ("'save'" in message or "'load'" in message)
    ):
        return ""
    return (
        "It was built for the path-based Recorder(save=..., load=...); rebuild it "
        "with Recorder(dumps=..., loads=...), or wrap its functions with "
        "ditto.recorders.recorder_from_files."
    )


RECORDER_REGISTRY: RecorderRegistry = RecorderRegistry()
"""Every installed recorder, keyed by name.

Names come from the `ditto_recorders` entry-point group, and each recorder is
imported the first time it is looked up. Add one in code with `register`.
"""
