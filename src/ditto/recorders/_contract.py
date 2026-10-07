import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence

from .._entry_points import (
    ContractProblem,
    Distribution,
    Registration,
    distributions_by_name,
    join_distributions as _join,
)


__all__ = (
    "NAME_PATTERN",
    "RESERVED_NAMES",
    "Distribution",
    "Registration",
    "ContractProblem",
    "find_name_problems",
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


# Registering distributions keyed by recorder name.
_ByName = Mapping[str, Sequence[Distribution]]


def find_name_problems(registrations: Iterable[Registration]) -> list[ContractProblem]:
    """Return the naming problems in a set of recorder registrations.

    Names outside the grammar are reported as invalid and are not checked
    further; the other rules apply to valid names only. Within each rule,
    problems are listed in name order, so the result does not depend on the
    order in which the registrations were found.
    """
    by_name = dict(sorted(distributions_by_name(registrations).items()))
    valid = {n: d for n, d in by_name.items() if NAME_PATTERN.fullmatch(n)}
    invalid = {n: d for n, d in by_name.items() if n not in valid}
    return [
        *_invalid_names(invalid),
        *_duplicated_names(valid),
        *_shadowing_names(valid),
        *_ambiguous_namespaces(valid),
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
            f"{_join(distributions)}. Snapshot files are named after their "
            "recorder, so the registrations would read and write each other's "
            "snapshots.",
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
