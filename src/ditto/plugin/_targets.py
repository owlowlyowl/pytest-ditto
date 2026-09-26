from __future__ import annotations

from collections.abc import Hashable, Mapping, MutableMapping
from pathlib import Path
from urllib.parse import urlparse

import fsspec
import fsspec.core
import pytest

from ditto.backends import BACKEND_REGISTRY, FsspecMapping
from ditto.exceptions import DittoUnhashableStorageOptionsError

from ._options import get_storage_options
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
    schemes.

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
    DittoUnhashableStorageOptionsError
        When `opts` contains a value that cannot be hashed.
    """
    canonical_uri = _canonicalize_uri(uri, test_dir)
    cache_key = _cache_key(canonical_uri, opts)

    if cache_key in state.backend_cache:
        return state.backend_cache[cache_key], canonical_uri

    canonical = urlparse(canonical_uri)
    scheme = canonical.scheme

    if scheme == "file":
        path = Path(canonical.netloc + canonical.path or ".ditto")
        backend = FsspecMapping(fsspec.filesystem("file"), path.as_posix())
        backend = maybe_enter(backend, state)
        state.backend_cache[cache_key] = backend
        return backend, canonical_uri

    if scheme in BACKEND_REGISTRY:
        backend = maybe_enter(BACKEND_REGISTRY[scheme](canonical_uri, **opts), state)
        state.backend_cache[cache_key] = backend
        return backend, canonical_uri

    if scheme in fsspec.available_protocols():
        fs, root = fsspec.core.url_to_fs(canonical_uri, **opts)
        backend = maybe_enter(FsspecMapping(fs, root), state)
        state.backend_cache[cache_key] = backend
        return backend, canonical_uri

    raise ValueError(
        f"Unknown backend scheme {scheme!r} in target URI {uri!r}. "
        f"To add support: install an fsspec extension for {scheme!r}, or register a "
        f"factory under the 'ditto_backends' entry-point group."
    )


def resolve_target(
    mark_target: str | None,
    mark_target_profile: str | None,
    request: pytest.FixtureRequest,
) -> tuple[MutableMapping[str, bytes], str]:
    """Resolve the snapshot storage target for this test.

    Precedence (first match wins):

    1. Mark `target=` — raw URI supplied directly on the mark.
    2. Mark `target_profile=` — named profile supplied on the mark.
    3. `ditto_target` ini — project-wide raw URI default.
    4. `ditto_target_profile` ini — project-wide named profile default.
    5. `file://.ditto` — built-in fallback.

    For raw URI paths, backend kwargs come from `ditto_storage_options` keyed
    by scheme. For profile paths, only the profile's own `storage_options` are
    used; `ditto_storage_options` is ignored.

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
    """
    fixturedefs = request._fixturemanager.getfixturedefs("ditto_backend", request.node)
    if fixturedefs:
        raise TypeError(
            "ditto_backend is superseded by target=, backend registration, and "
            "ditto_storage_options. Register a URI scheme under 'ditto_backends' "
            "and configure runtime options via ditto_storage_options."
        )

    test_dir = request.path.parent
    storage_options = get_storage_options(request)
    state = session_state(request.config)

    if mark_target is not None:
        parsed = urlparse(mark_target)
        return resolve_uri(
            mark_target, test_dir, storage_options.get(parsed.scheme, {}), state
        )

    if mark_target_profile is not None:
        profiles = load_target_profiles(request)
        profile_uri, profile_opts = resolve_profile(mark_target_profile, profiles)
        return resolve_uri(profile_uri, test_dir, profile_opts, state)

    ini_profile = request.config.getini("ditto_target_profile")
    if ini_profile:
        profiles = load_target_profiles(request)
        profile_uri, profile_opts = resolve_profile(ini_profile, profiles)
        return resolve_uri(profile_uri, test_dir, profile_opts, state)

    ini_target = request.config.getini("ditto_target") or "file://.ditto"
    parsed = urlparse(ini_target)
    return resolve_uri(
        ini_target, test_dir, storage_options.get(parsed.scheme, {}), state
    )
