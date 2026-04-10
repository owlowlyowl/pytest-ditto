from __future__ import annotations

import warnings
from collections.abc import MutableMapping
from contextlib import AbstractContextManager, ExitStack
from pathlib import Path
from typing import Any, cast

import pytest

from ditto import Snapshot
import fsspec

from ditto.backends import FsspecMapping
from ditto.snapshot import session_tracker
from ditto._report import render_session_report
from ditto.recorders import Recorder, RECORDER_REGISTRY, default as _default_recorder
from ditto.exceptions import AdditionalMarkError, DittoMarkHasNoIOType


__all__ = ("snapshot",)


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
_backend_cache: dict[str, MutableMapping[str, bytes]] = {}


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
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def snapshot(request: pytest.FixtureRequest) -> Snapshot:
    rootdir = request.config.rootpath
    module = request.path.relative_to(rootdir).with_suffix("").as_posix()
    marks = list(request.node.iter_markers(name="record"))
    recorder = _resolve_recorder(marks)
    update = request.config.getoption("--ditto-update", default=False)

    try:
        raw_backend = request.getfixturevalue("ditto_backend")
        backend = _maybe_enter(raw_backend)
        return Snapshot(
            module=module,
            group_name=request.node.name,
            recorder=recorder,
            backend=backend,
            update=update,
        )
    except pytest.FixtureLookupError as exc:
        if exc.argname != "ditto_backend":
            # A dependency of ditto_backend failed to resolve — re-raise so the
            # user sees the real error rather than silently falling back to local.
            raise exc from exc
        local_path = request.path.parent / ".ditto"
        # All tests in the same directory share one FsspecMapping instance so
        # they share one _BackendRecord in session_tracker. Without this cache,
        # each test gets a distinct object and Pass 1 of pytest_sessionfinish
        # treats every other test's files as "not accessed", deleting them all.
        cache_key = local_path.resolve().as_posix()
        if cache_key not in _backend_cache:
            _backend_cache[cache_key] = FsspecMapping(
                fsspec.filesystem("file"), local_path.as_posix()
            )
        backend = _backend_cache[cache_key]
        return Snapshot(
            module=module,
            group_name=request.node.name,
            recorder=recorder,
            backend=backend,
            update=update,
            path=local_path,  # kept for deprecated .path access; signals _filename_key
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
