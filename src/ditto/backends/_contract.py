import re
from collections.abc import Iterable, Mapping, Sequence

from .._entry_points import (
    ContractProblem,
    Distribution,
    Registration,
    distributions_by_name,
    join_distributions as _join,
)


__all__ = (
    "SCHEME_PATTERN",
    "UNREACHABLE_SCHEMES",
    "find_scheme_problems",
)


# An RFC 3986 scheme, lowercase because `urlparse` lowercases the schemes it reads.
SCHEME_PATTERN = re.compile(r"[a-z][a-z0-9+.\-]*")

# Schemes that target resolution handles before it consults the backend registry.
UNREACHABLE_SCHEMES = frozenset({"file"})


# Registering distributions keyed by scheme.
_ByScheme = Mapping[str, Sequence[Distribution]]


def find_scheme_problems(
    registrations: Iterable[Registration],
) -> list[ContractProblem]:
    """Return the problems in a set of backend registrations.

    Schemes outside the grammar are reported as invalid and are not checked
    further. Within each rule, problems are listed in scheme order, so the
    result does not depend on the order in which the registrations were found.
    """
    by_scheme = dict(sorted(distributions_by_name(registrations).items()))
    valid = {s: d for s, d in by_scheme.items() if SCHEME_PATTERN.fullmatch(s)}
    invalid = {s: d for s, d in by_scheme.items() if s not in valid}
    return [
        *_invalid_schemes(invalid),
        *_duplicated_schemes(valid),
        *_unreachable_schemes(valid),
    ]


def _invalid_schemes(by_scheme: _ByScheme) -> list[ContractProblem]:
    """Schemes no target URI can name."""
    return [
        ContractProblem(
            frozenset({scheme}),
            f"Backend scheme {scheme!r} from {_join(distributions)} is not valid: "
            "use a lowercase letter followed by lowercase letters, digits, '+', "
            "'-' or '.'.",
        )
        for scheme, distributions in by_scheme.items()
    ]


def _duplicated_schemes(by_scheme: _ByScheme) -> list[ContractProblem]:
    """Schemes registered more than once."""
    return [
        ContractProblem(
            frozenset({scheme}),
            f"Backend scheme {scheme!r} is registered more than once, by "
            f"{_join(distributions)}, so which one stores {scheme}:// targets is "
            "undefined. Uninstall all but one, or choose one by setting "
            f"ditto.backends.BACKEND_REGISTRY[{scheme!r}].",
        )
        for scheme, distributions in by_scheme.items()
        if len(distributions) > 1
    ]


def _unreachable_schemes(by_scheme: _ByScheme) -> list[ContractProblem]:
    """Schemes that target resolution never looks up."""
    return [
        ContractProblem(
            frozenset({scheme}),
            f"Backend scheme {scheme!r} from {_join(distributions)} is never used: "
            f"ditto stores {scheme}:// targets itself.",
        )
        for scheme, distributions in by_scheme.items()
        if scheme in UNREACHABLE_SCHEMES
    ]
