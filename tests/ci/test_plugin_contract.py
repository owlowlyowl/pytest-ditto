"""The plugin contract's naming and collision rules, checked from metadata."""

import pytest

import ditto
from ditto.recorders._contract import (
    NAME_PATTERN,
    RESERVED_NAMES,
    Registration,
    find_identifier_problems,
    find_legacy_problems,
    find_name_problems,
)


def _registrations(*pairs: tuple[str, str]) -> list[Registration]:
    return [Registration(name, distribution) for name, distribution in pairs]


@pytest.mark.parametrize("name", ["json", "pandas.csv", "my_fmt2", "ns.fmt_2"])
def test_accepts_bare_and_namespaced_names(name: str) -> None:
    """`<format>` and `<namespace>.<format>` names break no rule."""
    actual = find_name_problems(_registrations((name, "plug 2.0")))

    expected = []
    assert actual == expected


@pytest.mark.parametrize(
    "name", ["Pandas", "pandas-csv", "a.b.c", "_private", "2fmt", "pandas."]
)
def test_rejects_name_outside_the_grammar(name: str) -> None:
    """A name that is not `<format>` or `<namespace>.<format>` is a problem."""
    (problem,) = find_name_problems(_registrations((name, "plug 2.0")))

    assert problem.names == {name}
    assert "is not valid" in problem.message


def test_rejects_a_name_registered_by_two_distributions() -> None:
    """A duplicated name is a problem naming both distributions."""
    registrations = _registrations(("fmt", "plug-a 1.0"), ("fmt", "plug-b 2.0"))

    (problem,) = find_name_problems(registrations)

    assert problem.names == {"fmt"}
    assert "plug-a 1.0, plug-b 2.0" in problem.message


def test_rejects_a_bare_name_that_is_also_a_namespace() -> None:
    """`ns` and `ns.fmt` together make `ditto.ns` ambiguous, so all are affected."""
    registrations = _registrations(
        ("tabular", "plug-a 1.0"),
        ("tabular.csv", "plug-b 2.0"),
        ("tabular.parquet", "plug-b 2.0"),
    )

    (problem,) = find_name_problems(registrations)

    assert problem.names == {"tabular", "tabular.csv", "tabular.parquet"}
    assert "ditto.tabular is ambiguous" in problem.message


@pytest.mark.parametrize("name", ["record", "snapshot.csv", "version"])
def test_rejects_a_name_that_shadows_a_ditto_attribute(name: str) -> None:
    """A name whose first segment is a `ditto` attribute would be shadowed."""
    (problem,) = find_name_problems(_registrations((name, "plug 2.0")))

    assert problem.names == {name}
    assert "shadows ditto." in problem.message


def test_reserved_names_cover_every_public_ditto_attribute() -> None:
    """Every lowercase `ditto` attribute a recorder name could take is reserved."""
    attributes = {name for name in dir(ditto) if NAME_PATTERN.fullmatch(name)}

    unreserved = attributes - RESERVED_NAMES - {"json", "yaml"}

    assert unreserved == set()


def test_rejects_two_recorders_sharing_an_identifier() -> None:
    """Recorders with one identifier would share files, so both are affected."""
    identifiers = [
        (Registration("a.csv", "plug-a 1.0"), "csv"),
        (Registration("b.csv", "plug-b 2.0"), "csv"),
    ]

    (problem,) = find_identifier_problems(identifiers)

    assert problem.names == {"a.csv", "b.csv"}
    assert "'a.csv' (plug-a 1.0), 'b.csv' (plug-b 2.0)" in problem.message


def test_accepts_distinct_identifiers() -> None:
    """Recorders with different identifiers break no rule."""
    identifiers = [
        (Registration("pickle", "plug 2.0"), "pkl"),
        (Registration("json", "pytest-ditto 2.0"), "json"),
    ]

    actual = find_identifier_problems(identifiers)

    expected = []
    assert actual == expected


def test_reports_a_distribution_still_on_the_1x_contract() -> None:
    """A distribution registering `ditto_marks` is told which version to install."""
    (problem,) = find_legacy_problems(["pytest-ditto-pandas 0.1.1"])

    expected = (
        "pytest-ditto-pandas 0.1.1 uses the 1.x plugin contract; install "
        "pytest-ditto-pandas>=2.0."
    )
    assert problem.message == expected
