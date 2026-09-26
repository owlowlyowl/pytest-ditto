from __future__ import annotations

import tomllib
from collections.abc import Mapping
from typing import cast

import pytest

from ditto.exceptions import (
    DittoDuplicateProfileError,
    DittoInvalidProfileError,
    DittoUnknownProfileError,
)

from ._options import StorageOptions, get_optional_fixturevalue


__all__ = ("merge_profile_sources", "load_target_profiles", "resolve_profile")


def _get_target_profiles(request: pytest.FixtureRequest) -> dict[str, object]:
    """Return the `ditto_target_profiles` fixture value, or `{}` if absent.

    Parameters
    ----------
    request : pytest.FixtureRequest
        The active fixture request for the current test.

    Returns
    -------
    dict[str, Any]
        Profile table from the fixture, or an empty dict when the fixture
        is not defined.
    """
    profiles = get_optional_fixturevalue(request, "ditto_target_profiles")
    if profiles is None:
        return {}
    return cast(dict[str, object], profiles)


def _get_static_target_profiles(config: pytest.Config) -> dict[str, object]:
    """Return profiles from `[tool.pytest-ditto.target_profiles]` in `pyproject.toml`.

    Parameters
    ----------
    config : pytest.Config
        The active pytest configuration. `config.rootpath` is used to locate
        `pyproject.toml`.

    Returns
    -------
    dict[str, Any]
        Profile table from the TOML section, or an empty dict when
        `pyproject.toml` is absent or the section does not exist.
    """
    pyproject = config.rootpath / "pyproject.toml"
    if not pyproject.exists():
        return {}
    with pyproject.open("rb") as f:
        data = tomllib.load(f)
    return cast(
        dict[str, object],
        data.get("tool", {}).get("pytest-ditto", {}).get("target_profiles", {}),
    )


def merge_profile_sources(
    fixture_profiles: Mapping[str, object],
    static_profiles: Mapping[str, object],
) -> dict[str, object]:
    """Merge fixture and static profile tables into a single dict.

    Parameters
    ----------
    fixture_profiles : Mapping[str, Any]
        Profiles from the `ditto_target_profiles` fixture.
    static_profiles : Mapping[str, Any]
        Profiles from `pyproject.toml`.

    Returns
    -------
    dict[str, Any]
        Combined profile table.

    Raises
    ------
    DittoDuplicateProfileError
        When the same name appears in both sources. No precedence is applied;
        duplication is always an error.
    """
    duplicates = sorted(set(fixture_profiles) & set(static_profiles))
    if duplicates:
        raise DittoDuplicateProfileError(duplicates)
    return {**fixture_profiles, **static_profiles}


def load_target_profiles(request: pytest.FixtureRequest) -> dict[str, object]:
    """Return the combined target-profile table for the current test run."""
    return merge_profile_sources(
        _get_target_profiles(request),
        _get_static_target_profiles(request.config),
    )


def resolve_profile(
    name: str,
    profiles: Mapping[str, object],
) -> tuple[str, StorageOptions]:
    """Expand a named profile to `(uri, storage_options)`.

    Accepted profile shapes:

    - URI string shorthand: `"s3://bucket/prefix/"`
    - Full mapping: `{"uri": "s3://bucket/prefix/", "storage_options": {...}}`

    Parameters
    ----------
    name : str
        Profile name to look up.
    profiles : Mapping[str, Any]
        Combined profile table produced by `merge_profile_sources`.

    Returns
    -------
    tuple[str, dict[str, Any]]
        `(uri, storage_options)` where `storage_options` is an empty dict
        for shorthand profiles.

    Raises
    ------
    DittoUnknownProfileError
        When `name` is not present in `profiles`.
    DittoInvalidProfileError
        When the profile value is neither a URI string nor a mapping with a
        `uri` key, when the mapping carries keys other than `uri` and
        `storage_options`, or when `storage_options` is not a mapping.
    """
    if name not in profiles:
        raise DittoUnknownProfileError(name, list(profiles))

    value = profiles[name]

    match value:
        case str() as uri:
            return uri, {}
        case {"uri": str() as uri, **rest}:
            unknown = set(rest) - {"storage_options"}
            if unknown:
                raise DittoInvalidProfileError(
                    name,
                    f"unknown key(s) {', '.join(sorted(unknown))}; "
                    "allowed keys are uri and storage_options.",
                )

            raw_storage_options = rest.get("storage_options", {})
            if not isinstance(raw_storage_options, Mapping):
                raise DittoInvalidProfileError(
                    name,
                    "storage_options must be a mapping when provided.",
                )

            storage_options = dict(cast(Mapping[str, object], raw_storage_options))
            return uri, storage_options
        case {"uri": _}:
            raise DittoInvalidProfileError(name, "uri must be a string.")
        case _:
            raise DittoInvalidProfileError(name)
