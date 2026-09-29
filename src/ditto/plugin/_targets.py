from __future__ import annotations

from collections.abc import Hashable, Mapping, MutableMapping
from pathlib import Path
from typing import cast
from urllib.parse import urlparse

import fsspec
import fsspec.core
import pytest

from ditto.backends import BACKEND_REGISTRY, BackendFactory, FsspecMapping
from ditto.exceptions import (
    DittoBackendChangedError,
    DittoUnhashableStorageOptionsError,
)

from ._credentials import uri_credentials_error
from ._options import StorageOptions, get_storage_options
from ._profiles import load_target_profiles, resolve_profile
from ._session import DittoSession, TargetCacheKey, maybe_enter, session_state


__all__ = ("freeze_options", "resolve_uri", "resolve_target")


def freeze_options(value: object) -> Hashable:
    """Return a stable hashable representation of nested storage options.

    Raises
    ------
    DittoUnhashableStorageOptionsError
        When `value` (or something nested inside it) cannot be hashed.
    """
    if isinstance(value, Mapping):
        items = [(key, freeze_options(item)) for key, item in value.items()]
        return tuple(sorted(items, key=lambda item: repr(item[0])))
    if isinstance(value, (list, tuple)):
        return tuple(freeze_options(item) for item in value)
    if isinstance(value, set):
        return frozenset(freeze_options(item) for item in value)

    try:
        hash(value)
    except TypeError:
        raise DittoUnhashableStorageOptionsError(value) from None
    return value


def _canonicalize_uri(uri: str, test_dir: Path) -> str:
    """Return the canonical URI used for backend construction and caching."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return uri

    path_str = parsed.netloc + parsed.path or ".ditto"
    path = Path(path_str)
    if not path.is_absolute():
        path = (test_dir / path).resolve()
    return f"file://{path.as_posix()}"


# Backend sources for schemes that don't come from `BACKEND_REGISTRY`.
_FILE_SOURCE = object()
_FSSPEC_SOURCE = object()


def _backend_source(scheme: str) -> object:
    """Return what builds backends for `scheme`, in resolution order.

    Raises
    ------
    DittoBackendLoadError
        When the scheme's registered factory fails to load.
    DittoBackendConflictError
        When the scheme is registered more than once.
    """
    if scheme == "file":
        return _FILE_SOURCE
    if scheme in BACKEND_REGISTRY:
        return BACKEND_REGISTRY[scheme]
    return _FSSPEC_SOURCE


def _cache_key(
    canonical_uri: str,
    opts: Mapping[str, object],
) -> TargetCacheKey:
    """Return the per-session cache key for a resolved target.

    Raises
    ------
    DittoUnhashableStorageOptionsError
        When `opts` contains a value that cannot be hashed.
    """
    return canonical_uri, freeze_options(opts)


def resolve_uri(
    uri: str,
    test_dir: Path,
    opts: Mapping[str, object],
    state: DittoSession,
) -> tuple[MutableMapping[str, bytes], str]:
    """Resolve a URI to `(backend, canonical_uri)`.

    `canonical_uri` is fully-qualified for local `file://` targets and is used
    both for backend construction and for per-session backend caching.

    Resolution order (first match wins):

    1. `file://` — `FsspecMapping` on the local filesystem; relative paths
       resolve relative to `test_dir`; cached by canonical URI + opts.
    2. `BACKEND_REGISTRY` scheme — `factory(uri, **opts)`; for non-fsspec
       backends such as Redis, PostgreSQL, DuckDB.
    3. fsspec — `fsspec.core.url_to_fs(uri, **opts)`; covers S3, GCS, Azure,
       `memory://`, and all other fsspec protocols.
    4. Unknown — `ValueError` with an actionable install hint.

    `BACKEND_REGISTRY` is checked before fsspec so plugins can override fsspec
    schemes. A registered scheme whose factory fails to load, or that more than
    one plugin registers, raises rather than falling back to fsspec.

    Parameters
    ----------
    uri : str
        A URI string, e.g. `"file://.ditto"`, `"s3://bucket/prefix/"`,
        `"redis://localhost:6379/0"`.
    test_dir : Path
        Directory of the test file. Used to resolve relative `file://` paths.
    opts : Mapping[str, Any]
        Flat keyword arguments forwarded to the backend factory or
        `fsspec.core.url_to_fs`.
    state : DittoSession
        The session whose backend cache and exit stack own the backend.

    Returns
    -------
    tuple[MutableMapping[str, bytes], str]
        `(backend, canonical_uri)`.

    Raises
    ------
    ValueError
        When the scheme is unrecognised by both `BACKEND_REGISTRY` and fsspec.
    DittoBackendLoadError
        When the scheme's registered factory fails to load.
    DittoBackendConflictError
        When the scheme is registered more than once.
    DittoBackendChangedError
        When the scheme's backend source differs from the one that first built
        a backend for this URI in the session.
    DittoUnhashableStorageOptionsError
        When `opts` contains a value that cannot be hashed.
    """
    canonical_uri = _canonicalize_uri(uri, test_dir)
    cache_key = _cache_key(canonical_uri, opts)
    scheme = urlparse(canonical_uri).scheme

    source = _backend_source(scheme)
    first_source = state.backend_sources.get(canonical_uri, source)
    if first_source is not source:
        raise DittoBackendChangedError(scheme, canonical_uri)

    if cache_key in state.backend_cache:
        return state.backend_cache[cache_key], canonical_uri

    if source is _FILE_SOURCE:
        canonical = urlparse(canonical_uri)
        path = Path(canonical.netloc + canonical.path or ".ditto")
        backend = FsspecMapping(fsspec.filesystem("file"), path.as_posix())
    elif source is not _FSSPEC_SOURCE:
        factory = cast(BackendFactory, source)
        backend = factory(canonical_uri, **opts)
    elif scheme in fsspec.available_protocols():
        fs, root = fsspec.core.url_to_fs(canonical_uri, **opts)
        backend = FsspecMapping(fs, root)
    else:
        raise ValueError(
            f"Unknown backend scheme {scheme!r} in target URI {uri!r}. "
            f"To add support: install an fsspec extension for {scheme!r}, or "
            "register a factory under the 'ditto_backends' entry-point group."
        )

    backend = maybe_enter(backend, state)
    state.backend_cache[cache_key] = backend
    state.backend_sources[canonical_uri] = source
    return backend, canonical_uri


def _scheme_options(uri: str, request: pytest.FixtureRequest) -> StorageOptions:
    """Return the `ditto_storage_options` entry for `uri`'s scheme, or `{}`."""
    return get_storage_options(request).get(urlparse(uri).scheme, {})


def _select_target(
    mark_target: str | None,
    mark_target_profile: str | None,
    request: pytest.FixtureRequest,
) -> tuple[str, StorageOptions]:
    """Return the URI this test's snapshots use and the options to build it with.

    Precedence (first match wins):

    1. Mark `target=` — raw URI supplied directly on the mark.
    2. Mark `target_profile=` — named profile supplied on the mark.
    3. `ditto_target_profile` ini — project-wide named profile default.
    4. `ditto_target` ini — project-wide raw URI default.
    5. `file://.ditto` — built-in fallback.

    `ditto_target` and `ditto_target_profile` can't both be set, so 3 and 4
    never compete. For a raw URI the options come from `ditto_storage_options`
    keyed by scheme. For a profile only the profile's own `storage_options` are
    used; `ditto_storage_options` is ignored.
    """
    if mark_target is not None:
        return mark_target, _scheme_options(mark_target, request)
    if mark_target_profile is not None:
        return resolve_profile(mark_target_profile, load_target_profiles(request))
    if ini_profile := request.config.getini("ditto_target_profile"):
        return resolve_profile(ini_profile, load_target_profiles(request))
    ini_target = request.config.getini("ditto_target") or "file://.ditto"
    return ini_target, _scheme_options(ini_target, request)


def resolve_target(
    mark_target: str | None,
    mark_target_profile: str | None,
    request: pytest.FixtureRequest,
) -> tuple[MutableMapping[str, bytes], str]:
    """Resolve the snapshot storage target for this test.

    See `_select_target` for which target a test uses.

    Parameters
    ----------
    mark_target : str | None
        Raw URI from `target=` on the mark, or `None`.
    mark_target_profile : str | None
        Profile name from `target_profile=` on the mark, or `None`.
    request : pytest.FixtureRequest
        The active fixture request for the current test.

    Returns
    -------
    tuple[MutableMapping[str, bytes], str]
        `(backend, canonical_uri)`. The canonical URI is stored on
        `Snapshot.target` and drives storage key formatting.

    Raises
    ------
    TypeError
        When a `ditto_backend` fixture is detected (migration error).
    pytest.fail.Exception
        When the target URI contains a password or a secret query parameter.
        It is reported without a traceback, whose frames would show the URI.
    """
    fixturedefs = request._fixturemanager.getfixturedefs("ditto_backend", request.node)
    if fixturedefs:
        raise TypeError(
            "ditto_backend is superseded by target=, backend registration, and "
            "ditto_storage_options. Register a URI scheme under 'ditto_backends' "
            "and configure runtime options via ditto_storage_options."
        )

    uri, opts = _select_target(mark_target, mark_target_profile, request)
    if (message := uri_credentials_error(uri)) is not None:
        pytest.fail(message, pytrace=False)
    return resolve_uri(uri, request.path.parent, opts, session_state(request.config))
