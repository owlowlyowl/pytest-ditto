import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass


__all__ = (
    "NAME_PATTERN",
    "RESERVED_NAMES",
    "Registration",
    "ContractProblem",
    "find_name_problems",
    "find_identifier_problems",
    "find_legacy_problems",
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
class Registration:
    """One `ditto_recorders` entry point, as read from package metadata.

    Attributes
    ----------
    name : str
        The entry-point name, which is the recorder's user-facing name.
    distribution : str
        The registering distribution and its version, e.g. `"pytest-ditto 2.0.0"`.
    """

    name: str
    distribution: str


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


def find_name_problems(registrations: Iterable[Registration]) -> list[ContractProblem]:
    """Return the problems with a set of recorder registrations.

    Checks, from metadata alone: names that break the grammar, a name registered
    more than once, a bare name that is also a namespace, and a name whose first
    segment shadows an attribute of the `ditto` module.
    """
    by_name: dict[str, list[str]] = defaultdict(list)
    for registration in registrations:
        by_name[registration.name].append(registration.distribution)

    problems: list[ContractProblem] = []
    for name, distributions in by_name.items():
        if not NAME_PATTERN.fullmatch(name):
            problems.append(
                ContractProblem(
                    frozenset({name}),
                    f"Recorder name {name!r} from {_join(distributions)} is not "
                    "valid: use <format> or <namespace>.<format>, each segment a "
                    "lowercase letter followed by lowercase letters, digits or "
                    "underscores.",
                )
            )
            continue
        if len(distributions) > 1:
            problems.append(
                ContractProblem(
                    frozenset({name}),
                    f"Recorder name {name!r} is registered more than once, by "
                    f"{_join(distributions)}.",
                )
            )
        first_segment = name.partition(".")[0]
        if first_segment in RESERVED_NAMES:
            problems.append(
                ContractProblem(
                    frozenset({name}),
                    f"Recorder name {name!r} from {_join(distributions)} shadows "
                    f"ditto.{first_segment}; choose another name.",
                )
            )

    valid = [name for name in by_name if NAME_PATTERN.fullmatch(name)]
    for namespace in sorted({n.partition(".")[0] for n in valid if "." in n}):
        if namespace not in by_name:
            continue
        members = sorted(n for n in valid if n.startswith(f"{namespace}."))
        member_distributions = [d for n in members for d in by_name[n]]
        problems.append(
            ContractProblem(
                frozenset({namespace, *members}),
                f"{namespace!r} is both a recorder name (from "
                f"{_join(by_name[namespace])}) and a namespace ({', '.join(members)} "
                f"from {_join(member_distributions)}), so ditto.{namespace} is "
                "ambiguous.",
            )
        )
    return problems


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


def find_legacy_problems(marks_distributions: Iterable[str]) -> list[ContractProblem]:
    """Return a problem for each distribution still on the 1.x plugin contract.

    Parameters
    ----------
    marks_distributions : Iterable[str]
        The name and version (`"<name> <version>"`) of each distribution that
        registers the removed `ditto_marks` entry-point group.
    """
    return [
        ContractProblem(
            frozenset(),
            f"{distribution} uses the 1.x plugin contract; install "
            f"{distribution.partition(' ')[0]}>=2.0.",
        )
        for distribution in sorted(set(marks_distributions))
    ]


def _join(distributions: Iterable[str]) -> str:
    return ", ".join(sorted(set(distributions)))


def _describe(registrations: Iterable[Registration]) -> str:
    return ", ".join(
        f"{r.name!r} ({r.distribution})"
        for r in sorted(registrations, key=lambda r: r.name)
    )
