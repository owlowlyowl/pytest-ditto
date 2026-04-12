from __future__ import annotations

import warnings
from collections.abc import Hashable, MutableMapping
from contextlib import AbstractContextManager, ExitStack
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import pytest

from ditto import Snapshot
import fsspec
import fsspec.core

from ditto.backends import FsspecMapping
from ditto.snapshot import session_tracker
from ditto._report import render_session_report
from ditto.recorders import Recorder, RECORDER_REGISTRY, default as _default_recorder
from ditto.exceptions import AdditionalMarkError, DittoMarkHasNoIOType


__all__ = ("snapshot",)


TargetCacheKey = tuple[str, Hashable]


# ---------------------------------------------------------------------------
# Module-level session state — reset in pytest_sessionstart
#
# Pytest hook functions (pytest_sessionstart, pytest_sessionfinish, etc.) are
# discovered and called by pytest's plugin machinery with no dependency-injection
# mechanism for passing state between them. Module-level variables are the only
# practical way to share lifecycle state across hooks in a pytest plugin.
# ---------------------------------------------------------------------------

_session_exit_stack: ExitStack = ExitStack()
_entered_backends: dict[int, MutableMapping[str, bytes]] = {}
_backend_cache: dict[TargetCacheKey, MutableMapping[str, bytes]] = {}


# ---------------------------------------------------------------------------
# Backend lifecycle
# ---------------------------------------------------------------------------


def _maybe_enter(backend: MutableMapping[str, bytes]) -> MutableMapping[str, bytes]:
    """Enter a context-manager backend into the session `ExitStack` exactly once.

    Returns the value of `__enter__` (typically `self`). No-op for backends that
    are not context managers and for backends already entered.
    """
    bid = id(backend)
    if bid in _entered_backends:
        return _entered_backends[bid]
    if isinstance(backend, AbstractContextManager):
        entered = cast(
            MutableMapping[str, bytes],
            _session_exit_stack.enter_context(backend),
        )
        _entered_backends[bid] = entered
        return entered
    return backend


# ---------------------------------------------------------------------------
# Mark resolution
# ---------------------------------------------------------------------------


def _resolve_recorder(marks: list) -> Recorder:
    """Resolve the recorder from a list of pytest marks.

    Raises
    ------
    AdditionalMarkError
        If more than one `record` mark is present on the test.
    DittoMarkHasNoIOType
        If the mark carries no arguments or names an unregistered recorder.
    """
    match len(marks):
        case 0:
            return _default_recorder()
        case 1:
            if not marks[0].args or marks[0].args[0] not in RECORDER_REGISTRY:
                raise DittoMarkHasNoIOType()
            return RECORDER_REGISTRY[marks[0].args[0]]
        case _:
            raise AdditionalMarkError()


# ---------------------------------------------------------------------------
# URI resolution engine
# ---------------------------------------------------------------------------


def _parse_mark_target(marks: list) -> str | None:
    """Return the target= URI from the record mark, or None if absent."""
    if not marks:
        return None
    return marks[0].kwargs.get("target")


def _get_storage_options(request: pytest.FixtureRequest) -> dict[str, dict]:
    """Return per-scheme storage options from ditto_storage_options, or {}."""
    try:
        return request.getfixturevalue("ditto_storage_options")
    except pytest.FixtureLookupError:
        return {}


def _freeze_options(value: Any) -> Hashable:
    """Return a stable hashable representation of nested storage options."""
    if isinstance(value, dict):
        items = [
            (key, _freeze_options(item)) for key, item in value.items()
        ]
        return tuple(sorted(items, key=lambda item: repr(item[0])))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_options(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze_options(item) for item in value)

    hash(value)
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


def _cache_key(canonical_uri: str, opts: dict[str, Any]) -> TargetCacheKey | None:
    """Return the per-session cache key for a resolved target, or None."""
    try:
        return canonical_uri, _freeze_options(opts)
    except TypeError:
        return None


def _resolve_uri(
    uri: str,
    test_dir: Path,
    storage_options: dict[str, dict],
) -> tuple[MutableMapping[str, bytes], str]:
    """Resolve a URI to (backend, canonical_uri).

    canonical_uri is always fully-qualified for local `file://` targets and is
    used both for backend construction and for per-session backend caching.

    **Resolution order** (first match wins)
    1. file://   — FsspecMapping on local filesystem; relative paths resolve
                   relative to test_dir; result is cached by canonical URI + opts.
    2. BACKEND_REGISTRY scheme — factory(uri, **opts); for non-fsspec backends
                   such as Redis, PostgreSQL, DuckDB.
    3. fsspec    — fsspec.core.url_to_fs(uri, **opts); covers S3, GCS, Azure,
                   memory://, and all other fsspec protocols.
    4. Unknown   — ValueError with an actionable install hint.

    BACKEND_REGISTRY is checked before fsspec so plugins can override fsspec schemes.

    Parameters
    ----------
    uri : str
        A URI string, e.g. "file://.ditto", "s3://bucket/prefix/",
        "redis://localhost:6379/0", "duckdb:///:memory:".
    test_dir : Path
        Directory of the test file. Used to resolve relative file:// paths.
    storage_options : dict[str, dict]
        Per-scheme kwargs from the ditto_storage_options fixture. The entry
        keyed by the URI scheme is unpacked as kwargs into the factory or
        fsspec.core.url_to_fs.

    Raises
    ------
    ValueError
        When the scheme is unrecognised by both BACKEND_REGISTRY and fsspec.
    """
    from ditto.backends import BACKEND_REGISTRY

    parsed = urlparse(uri)
    scheme = parsed.scheme
    opts = storage_options.get(scheme, {})
    canonical_uri = _canonicalize_uri(uri, test_dir)
    cache_key = _cache_key(canonical_uri, opts)

    if cache_key is not None and cache_key in _backend_cache:
        return _backend_cache[cache_key], canonical_uri

    canonical = urlparse(canonical_uri)
    scheme = canonical.scheme

    if scheme == "file":
        path = Path(canonical.netloc + canonical.path or ".ditto")
        backend = FsspecMapping(fsspec.filesystem("file"), path.as_posix())
        backend = _maybe_enter(backend)
        if cache_key is not None:
            _backend_cache[cache_key] = backend
        return backend, canonical_uri

    if scheme in BACKEND_REGISTRY:
        backend = _maybe_enter(BACKEND_REGISTRY[scheme](canonical_uri, **opts))
        if cache_key is not None:
            _backend_cache[cache_key] = backend
        return backend, canonical_uri

    if scheme in fsspec.available_protocols():
        fs, root = fsspec.core.url_to_fs(canonical_uri, **opts)
        backend = _maybe_enter(FsspecMapping(fs, root))
        if cache_key is not None:
            _backend_cache[cache_key] = backend
        return backend, canonical_uri

    raise ValueError(
        f"Unknown backend scheme {scheme!r} in target URI {uri!r}. "
        f"To add support: install an fsspec extension for {scheme!r}, or register a "
        f"factory under the 'ditto_backends' entry-point group."
    )


def _resolve_target(
    target_uri: str | None,
    request: pytest.FixtureRequest,
) -> tuple[MutableMapping[str, bytes], str]:
    """Resolve the snapshot storage target for this test.

    Implements the full precedence chain:

        mark target=  →  ditto_target ini  →  file://.ditto

    Returns (backend, canonical_uri). The canonical URI is passed to
    `Snapshot.target` and drives key-format selection.
    """
    fixturedefs = request._fixturemanager.getfixturedefs("ditto_backend", request.node)
    if fixturedefs:
        raise TypeError(
            "ditto_backend is superseded by target=, backend registration, and "
            "ditto_storage_options. Register a URI scheme under 'ditto_backends' "
            "and configure runtime options via ditto_storage_options."
        )

    test_dir = request.path.parent
    opts = _get_storage_options(request)

    if target_uri is not None:
        return _resolve_uri(target_uri, test_dir, opts)

    ini_uri = request.config.getini("ditto_target")
    return _resolve_uri(ini_uri, test_dir, opts)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def snapshot(request: pytest.FixtureRequest) -> Snapshot:
    rootdir = request.config.rootpath
    module = request.path.relative_to(rootdir).with_suffix("").as_posix()
    marks = list(request.node.iter_markers(name="record"))
    recorder = _resolve_recorder(marks)
    update = request.config.getoption("--ditto-update", default=False)

    target_uri = _parse_mark_target(marks)
    backend, abs_uri = _resolve_target(target_uri, request)

    return Snapshot(
        module=module,
        group_name=request.node.name,
        target=abs_uri,
        _backend=backend,
        recorder=recorder,
        update=update,
    )


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("ditto")
    group.addoption(
        "--ditto-update",
        action="store_true",
        default=False,
        help="Overwrite all existing snapshots with current test values.",
    )
    group.addoption(
        "--ditto-prune",
        action="store_true",
        default=False,
        help="After the session, delete snapshot files not accessed during this run.",
    )
    parser.addini(
        "ditto_target",
        help=(
            "Default snapshot storage URI for all tests in this project. "
            "Examples: 's3://my-bucket/ditto', 'file://.ditto'. "
            "Relative file:// paths resolve relative to the test file. "
            "Credentials come from the ditto_storage_options fixture."
        ),
        default="file://.ditto",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "record(recorder): snapshot with a specific recorder",
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    global _session_exit_stack
    _session_exit_stack = ExitStack()
    _entered_backends.clear()
    _backend_cache.clear()
    session_tracker.reset()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    config = session.config
    do_prune = config.getoption("--ditto-prune", default=False)
    rootdir = config.rootpath

    pruned: list[str] = []
    unused: list[str] = []

    # FIXME: The .root attribute is a brittle duck-typed contract for detecting
    # filesystem-backed backends. Any custom backend that happens to expose a
    # .root attribute (even a non-filesystem one) will be treated as a local
    # directory and added to the registered_fs_roots set, potentially causing
    # Pass 2 to skip stale-directory scanning for paths it shouldn't own.
    # A typed protocol (e.g. SupportsRoot) or an explicit registry would make
    # this contract visible and enforceable.
    def _get_root(backend: Any) -> Path | None:
        root_attr = getattr(backend, "root", None)
        if root_attr is not None:
            return Path(root_attr).resolve()

        # Unwrap PrefixedMapping and TransformMapping
        inner = getattr(backend, "_store", getattr(backend, "_mapping", None))
        if inner is not None:
            return _get_root(inner)
        return None

    # Pass 1 — iterate backends registered in session_tracker.
    # Connections are still alive here; ExitStack closes after this hook.
    registered_fs_roots: set[Path] = set()
    for record in session_tracker.records.values():
        root = _get_root(record.backend)
        if root is not None:
            registered_fs_roots.add(root)

        accessed_keys = {record.key_of(k) for k in record.accessed}
        try:
            all_keys = set(record.backend)
        except NotImplementedError:
            warnings.warn(
                f"Backend {record.backend!r} does not support enumeration; "
                "skipping unused-snapshot detection for this backend.",
                stacklevel=1,
            )
            continue
        except Exception as exc:
            # Covers I/O errors from remote backends (FileNotFoundError,
            # PermissionError, ConnectionError, etc.) raised by __iter__
            # implementations such as FsspecMapping's fs.find() call.
            warnings.warn(
                f"Backend {record.backend!r} raised {type(exc).__name__} during "
                f"enumeration: {exc}; skipping unused-snapshot "
                "detection for this backend.",
                stacklevel=1,
            )
            continue

        not_accessed = all_keys - accessed_keys
        for raw_key in sorted(not_accessed):
            if do_prune:
                # Catch all backend errors so a single failed delete (e.g.
                # PermissionError on a read-only mount, OSError from a dropped
                # network share) does not abort the loop and leave the session
                # report unrendered. Warn per failure and continue.
                try:
                    del record.backend[raw_key]
                except Exception as exc:
                    warnings.warn(
                        f"Failed to prune snapshot {raw_key!r}: {exc}",
                        stacklevel=1,
                    )
                else:
                    pruned.append(raw_key)
            else:
                unused.append(raw_key)

    # Pass 2 — discover .ditto/ directories not touched this session.
    # Catches stale snapshots from test files that were deleted or renamed.
    #
    # Gated on do_prune rather than "do_prune or session_tracker.records":
    # the broader condition fires on any partial run (e.g. pytest tests/foo.py),
    # where every .ditto/ directory belonging to un-run tests appears as a ghost
    # and all their snapshots are falsely reported as unused. Ghost detection is
    # a cleanup operation and only makes sense when the user has explicitly asked
    # for it. If a non-destructive "unused" report for ghost directories is ever
    # needed, add a dedicated --ditto-check-ghosts flag rather than coupling it
    # to session_tracker.records.
    if do_prune:
        for ditto_dir in rootdir.rglob(".ditto"):
            if not ditto_dir.is_dir():
                continue
            if ditto_dir.resolve() in registered_fs_roots:
                continue
            ghost = FsspecMapping(fsspec.filesystem("file"), ditto_dir.as_posix())
            try:
                ghost_keys = sorted(ghost)
            except Exception as exc:
                warnings.warn(
                    f"Failed to enumerate ghost directory {ditto_dir!r}: {exc}; "
                    "skipping unused-snapshot detection for this directory.",
                    stacklevel=1,
                )
                continue
            for raw_key in ghost_keys:
                if do_prune:
                    # Same rationale as Pass 1: don't let a single delete
                    # failure abort the loop or swallow the session report.
                    try:
                        del ghost[raw_key]
                    except Exception as exc:
                        warnings.warn(
                            f"Failed to prune snapshot {raw_key!r}: {exc}",
                            stacklevel=1,
                        )
                    else:
                        pruned.append(raw_key)
                else:
                    unused.append(raw_key)

    render_session_report(
        created=session_tracker.created,
        updated=session_tracker.updated,
        pruned=pruned,
        unused=unused,
    )


def pytest_unconfigure(config: pytest.Config) -> None:
    """Close all backend connections after pruning has run in pytest_sessionfinish."""
    _session_exit_stack.close()
