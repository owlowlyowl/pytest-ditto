from __future__ import annotations

import importlib.metadata
from collections.abc import Callable, Iterable, Iterator, MutableMapping
from importlib.metadata import EntryPoint
from typing import cast

from ._contract import find_scheme_problems
from .._entry_points import (
    ContractProblem,
    Distribution,
    LazyEntryPoints,
    Registration,
)
from ..exceptions import DittoBackendConflictError, DittoBackendLoadError


__all__ = ("BACKEND_REGISTRY", "BackendFactory", "BackendRegistry")


BackendFactory = Callable[..., MutableMapping[str, bytes]]

# Stands in for a distribution in contract messages about schemes set on a
# `BackendRegistry`.
LOCAL_REGISTRATION = Distribution("BACKEND_REGISTRY", "")


class BackendRegistry(MutableMapping[str, BackendFactory]):
    """
    Backend factories keyed by URI scheme, imported only when first looked up.

    Each factory has the signature
    `factory(uri: str, **storage_options) -> MutableMapping[str, bytes]`.

    Schemes come from `ditto_backends` entry-point metadata, which needs no
    import, so membership tests, iteration and `problems` never import a
    plugin. Every registration is checked against the plugin contract when the
    registry is built. Looking up a scheme a problem affects raises
    `DittoBackendConflictError`, so the registry never picks one of the
    conflicting registrations.

    Setting a scheme overrides any factory discovered for it, and resolves its
    conflict. Deleting a scheme removes the override, restoring the discovered
    factory; a discovered factory cannot be deleted. Iteration preserves
    discovery order, followed by schemes set only on the registry.

    Looking up values (including through `get`, `items` or `values`) can load
    plugins and raise `DittoBackendLoadError` or `DittoBackendConflictError`.

    Parameters
    ----------
    entry_points : Iterable[EntryPoint], optional
        Entry points to serve. Defaults to the installed `ditto_backends` group.
    """

    def __init__(self, entry_points: Iterable[EntryPoint] | None = None) -> None:
        if entry_points is None:
            entry_points = importlib.metadata.entry_points(group="ditto_backends")
        self._discovered = LazyEntryPoints(entry_points, _check_factory, _load_error)
        self._problems = tuple(find_scheme_problems(self._discovered.registrations))
        self._conflicts = {
            scheme: problem for problem in self._problems for scheme in problem.names
        }
        self._overrides: dict[str, BackendFactory] = {}

    @property
    def problems(self) -> tuple[ContractProblem, ...]:
        """Every contract problem among the registrations, found without imports."""
        return self._problems

    def __getitem__(self, scheme: str) -> BackendFactory:
        if scheme in self._overrides:
            return self._overrides[scheme]
        if scheme in self._conflicts:
            raise DittoBackendConflictError(self._conflicts[scheme].message)
        return self._discovered.load(scheme)

    def __setitem__(self, scheme: str, factory: BackendFactory) -> None:
        """Handle `scheme` with `factory`, overriding any discovered factory.

        Raises
        ------
        TypeError
            If `factory` is not callable.
        DittoBackendConflictError
            If no target URI can reach `scheme`.
        """
        if not callable(factory):
            raise TypeError(f"{type(factory).__name__} is not callable")
        problems = find_scheme_problems([Registration(scheme, LOCAL_REGISTRATION)])
        if problems:
            raise DittoBackendConflictError(
                " ".join(problem.message for problem in problems)
            )
        self._overrides[scheme] = factory

    def __delitem__(self, scheme: str) -> None:
        del self._overrides[scheme]

    def __contains__(self, scheme: object) -> bool:
        return scheme in self._overrides or scheme in self._discovered

    def __iter__(self) -> Iterator[str]:
        yield from self._discovered
        yield from (s for s in self._overrides if s not in self._discovered)

    def __len__(self) -> int:
        return sum(1 for _ in self)


def _check_factory(entry: EntryPoint, factory: object) -> BackendFactory:
    if not callable(factory):
        raise TypeError(f"{entry.value} is a {type(factory).__name__}, not callable")
    # Only callability can be checked before the factory is called.
    return cast(BackendFactory, factory)


def _load_error(
    entry: EntryPoint, distribution: Distribution, exc: Exception
) -> DittoBackendLoadError:
    return DittoBackendLoadError(entry.name, str(distribution), exc)


BACKEND_REGISTRY: BackendRegistry = BackendRegistry()
