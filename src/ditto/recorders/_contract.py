import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass


__all__ = (
    "NAME_PATTERN",
    "RESERVED_NAMES",
    "Distribution",
    "Registration",
    "ContractProblem",
    "find_name_problems",
    "find_identifier_problems",
    "find_legacy_problems",
    "upgrade_message",
)


# `<format>` or `<namespace>.<format>`; each segment starts with a lowercase letter.
NAME_PATTERN = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)?")

# Attributes of the `ditto` module that a recorder name must not shadow. Core's own
# recorders (`json`, `yaml`) are not listed: their convenience marks are the marks
# their names derive.
RESERVED_NAMES = frozenset({
    "backends",
    "cli",
    "exceptions",
    "plugin",
    "record",
    "recorders",
    "snapshot",
    "version",
})


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
    """One `ditto_recorders` entry point, as read from package metadata.

    Attributes
    ----------
    name : str
        The entry-point name, which is the recorder's user-facing name.
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
        The recorder names the problem makes unusable.
    message : str
        What is wrong, naming the distributions involved.
    """

    names: frozenset[str]
    message: str


# Registering distributions keyed by recorder name.
_ByName = Mapping[str, Sequence[Distribution]]


def find_name_problems(registrations: Iterable[Registration]) -> list[ContractProblem]:
    """Return the naming problems in a set of recorder registrations.

    Names outside the grammar are reported as invalid and are not checked
    further; the other rules apply to valid names only.
    """
    by_name = _distributions_by_name(registrations)
    valid = {n: d for n, d in by_name.items() if NAME_PATTERN.fullmatch(n)}
    invalid = {n: d for n, d in by_name.items() if n not in valid}
    return [
        *_invalid_names(invalid),
        *_duplicated_names(valid),
        *_shadowing_names(valid),
        *_ambiguous_namespaces(valid),
    ]


def find_identifier_problems(
    identifiers: Iterable[tuple[Registration, str]],
) -> list[ContractProblem]:
    """Return the problems with recorders' persisted identifiers.

    Two recorders with the same identifier would read and write each other's
    snapshot files.

    Parameters
    ----------
    identifiers : Iterable[tuple[Registration, str]]
        Each loaded recorder's registration and its `Recorder.identifier`.
    """
    by_identifier: dict[str, list[Registration]] = defaultdict(list)
    for registration, identifier in identifiers:
        by_identifier[identifier].append(registration)

    return [
        ContractProblem(
            frozenset(r.name for r in registrations),
            f"Recorders {_describe(registrations)} share the identifier "
            f"{identifier!r}, so they would read and write each other's snapshot "
            "files.",
        )
        for identifier, registrations in by_identifier.items()
        if len(registrations) > 1
    ]


def find_legacy_problems(
    marks_distributions: Iterable[Distribution],
) -> list[ContractProblem]:
    """Return a problem for each distribution still on the 1.x plugin contract.

    Parameters
    ----------
    marks_distributions : Iterable[Distribution]
        Each distribution that registers the removed `ditto_marks` group.
    """
    return [
        ContractProblem(frozenset(), upgrade_message(distribution))
        for distribution in sorted(set(marks_distributions), key=str)
    ]


def upgrade_message(distribution: Distribution) -> str:
    """Return the message telling a 1.x plugin's users which version to install."""
    return (
        f"{distribution} uses the 1.x plugin contract; install "
        f"{distribution.name}>=2.0."
    )


def _distributions_by_name(
    registrations: Iterable[Registration],
) -> dict[str, list[Distribution]]:
    by_name: dict[str, list[Distribution]] = defaultdict(list)
    for registration in registrations:
        by_name[registration.name].append(registration.distribution)
    return by_name


def _invalid_names(by_name: _ByName) -> list[ContractProblem]:
    """Names that are not `<format>` or `<namespace>.<format>`."""
    return [
        ContractProblem(
            frozenset({name}),
            f"Recorder name {name!r} from {_join(distributions)} is not valid: "
            "use <format> or <namespace>.<format>, each segment a lowercase "
            "letter followed by lowercase letters, digits or underscores.",
        )
        for name, distributions in by_name.items()
    ]


def _duplicated_names(by_name: _ByName) -> list[ContractProblem]:
    """Names registered more than once."""
    return [
        ContractProblem(
            frozenset({name}),
            f"Recorder name {name!r} is registered more than once, by "
            f"{_join(distributions)}.",
        )
        for name, distributions in by_name.items()
        if len(distributions) > 1
    ]


def _shadowing_names(by_name: _ByName) -> list[ContractProblem]:
    """Names whose first segment is an attribute of the `ditto` module."""
    return [
        ContractProblem(
            frozenset({name}),
            f"Recorder name {name!r} from {_join(distributions)} shadows "
            f"ditto.{_namespace(name)}; choose another name.",
        )
        for name, distributions in by_name.items()
        if _namespace(name) in RESERVED_NAMES
    ]


def _ambiguous_namespaces(by_name: _ByName) -> list[ContractProblem]:
    """Bare names that are also the namespace of other names."""
    members: dict[str, list[str]] = defaultdict(list)
    for name in by_name:
        if "." in name:
            members[_namespace(name)].append(name)

    return [
        ContractProblem(
            frozenset({namespace, *names}),
            f"{namespace!r} is both a recorder name (from "
            f"{_join(by_name[namespace])}) and a namespace ({', '.join(sorted(names))} "
            f"from {_join(d for n in names for d in by_name[n])}), so "
            f"ditto.{namespace} is ambiguous.",
        )
        for namespace, names in sorted(members.items())
        if namespace in by_name
    ]


def _namespace(name: str) -> str:
    return name.partition(".")[0]


def _join(distributions: Iterable[Distribution]) -> str:
    return ", ".join(sorted({str(d) for d in distributions}))


def _describe(registrations: Iterable[Registration]) -> str:
    return ", ".join(
        f"{r.name!r} ({r.distribution})"
        for r in sorted(registrations, key=lambda r: r.name)
    )
