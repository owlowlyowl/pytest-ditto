"""Discovery and lazy loading of ditto's entry-point plugins.

Shared by the recorder and backend registries. Each registry keeps its own
contract rules and error types; this module only records who registered each
name and imports a name's entry point on first use.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from importlib.metadata import EntryPoint
from typing import Generic, TypeVar


__all__ = (
    "ContractProblem",
    "Distribution",
    "LazyEntryPoints",
    "Registration",
    "distribution_of",
    "distributions_by_name",
    "join_distributions",
)

T = TypeVar("T")


@dataclass(frozen=True)
class Distribution:
    """An installed distribution, as named in contract messages.

    Attributes
    ----------
    name : str
        The distribution's name, e.g. `"pytest-ditto-pandas"`.
    version : str
        Its version, or `""` when unknown.
    """

    name: str
    version: str

    def __str__(self) -> str:
        return f"{self.name} {self.version}" if self.version else self.name


@dataclass(frozen=True)
class Registration:
    """One entry point, as read from package metadata.

    Attributes
    ----------
    name : str
        The entry-point name, which is the plugin's user-facing name.
    distribution : Distribution
        The distribution that registers it.
    """

    name: str
    distribution: Distribution


@dataclass(frozen=True)
class ContractProblem:
    """A breach of the plugin contract.

    Attributes
    ----------
    names : frozenset[str]
        The names the problem makes unusable.
    message : str
        What is wrong, naming the distributions involved.
    """

    names: frozenset[str]
    message: str


def distribution_of(entry: EntryPoint) -> Distribution:
    """Return the distribution registering `entry`."""
    if entry.dist is None:
        return Distribution("an unknown distribution", "")
    return Distribution(entry.dist.name, entry.dist.version)


def distributions_by_name(
    registrations: Iterable[Registration],
) -> dict[str, list[Distribution]]:
    """Return the registering distributions keyed by name, in discovery order."""
    by_name: dict[str, list[Distribution]] = defaultdict(list)
    for registration in registrations:
        by_name[registration.name].append(registration.distribution)
    return dict(by_name)


def join_distributions(distributions: Iterable[Distribution]) -> str:
    """Name each distinct distribution once, in sorted order."""
    return ", ".join(sorted({str(d) for d in distributions}))


class LazyEntryPoints(Generic[T]):
    """
    Entry points keyed by name, each imported only when first loaded.

    Names and distributions come from metadata, so membership tests, iteration
    and `registrations` never import a plugin. When a name is registered more
    than once, the first entry point is the one loaded; callers report the
    duplicate as a contract problem rather than rely on that choice.

    Parameters
    ----------
    entry_points : Iterable[EntryPoint]
        Entry points to serve.
    check : Callable[[EntryPoint, object], T]
        Called with each loaded object; returns it as a `T`, or raises if it
        is not one.
    error : Callable[[EntryPoint, Distribution, Exception], Exception]
        Builds the exception raised when loading or `check` fails. It is
        raised from the original exception.
    """

    def __init__(
        self,
        entry_points: Iterable[EntryPoint],
        check: Callable[[EntryPoint, object], T],
        error: Callable[[EntryPoint, Distribution, Exception], Exception],
    ) -> None:
        entry_points = list(entry_points)
        self.registrations = tuple(
            Registration(ep.name, distribution_of(ep)) for ep in entry_points
        )
        self._entries: dict[str, EntryPoint] = {}
        for ep in entry_points:
            self._entries.setdefault(ep.name, ep)
        self._check = check
        self._error = error
        self._loaded: dict[str, T] = {}

    def load(self, name: str) -> T:
        """Return the object registered under `name`, importing it on first use.

        Raises
        ------
        KeyError
            If no entry point is registered under `name`.
        """
        if name not in self._loaded:
            self._loaded[name] = self._load(self._entries[name])
        return self._loaded[name]

    def __contains__(self, name: object) -> bool:
        return name in self._entries

    def __iter__(self) -> Iterator[str]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __copy__(self) -> "LazyEntryPoints[T]":
        """Copy the entry points and the objects loaded so far."""
        copied = LazyEntryPoints([], self._check, self._error)
        copied.registrations = self.registrations
        copied._entries = self._entries.copy()
        copied._loaded = self._loaded.copy()
        return copied

    def _load(self, entry: EntryPoint) -> T:
        try:
            return self._check(entry, entry.load())
        except Exception as exc:
            raise self._error(entry, distribution_of(entry), exc) from exc
