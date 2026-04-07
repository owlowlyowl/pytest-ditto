from __future__ import annotations

import warnings
from collections.abc import MutableMapping
from contextlib import AbstractContextManager, ExitStack
from pathlib import Path

import pytest

from ditto import Snapshot
from ditto.backends import LocalMapping
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
_entered_backend_ids: set[int] = set()
_backend_cache: dict[str, MutableMapping[str, bytes]] = {}


# ---------------------------------------------------------------------------
# Backend lifecycle
# ---------------------------------------------------------------------------


def _maybe_enter(backend: MutableMapping[str, bytes]) -> MutableMapping[str, bytes]:
    """Enter a context-manager backend into the session ExitStack exactly once.

    Returns the value of __enter__ (typically self). No-op for backends that
    are not context managers and for backends already entered.
    """
    bid = id(backend)
    if bid not in _entered_backend_ids and isinstance(backend, AbstractContextManager):
        entered = _session_exit_stack.enter_context(backend)
        _entered_backend_ids.add(bid)
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
    rootdir = Path(request.config.rootdir)
    module = str(request.path.relative_to(rootdir).with_suffix(""))
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
    except pytest.FixtureLookupError:
        local_path = request.path.parent / ".ditto"
        return Snapshot(
            module=module,
            group_name=request.node.name,
            recorder=recorder,
            backend=LocalMapping(local_path),
            update=update,
            path=local_path,  # kept for deprecated .path access; signals filename key_of
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
        "record(recorder, backend=None): snapshot values with optional backend override",
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    global _session_exit_stack
    _session_exit_stack = ExitStack()
    _entered_backend_ids.clear()
    _backend_cache.clear()
    session_tracker.reset()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    config = session.config
    do_prune = config.getoption("--ditto-prune", default=False)
    rootdir = config.rootpath

    pruned: list[str] = []
    unused: list[str] = []

    # Pass 1 — iterate backends registered in session_tracker.
    # Connections are still alive here; ExitStack closes after this hook.
    registered_fs_roots: set[Path] = set()
    for record in session_tracker.records.values():
        root = getattr(record.backend, "root", None)
        if root is not None:
            registered_fs_roots.add(Path(root).resolve())

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

        not_accessed = all_keys - accessed_keys
        for raw_key in sorted(not_accessed):
            if do_prune:
                del record.backend[raw_key]
                pruned.append(raw_key)
            else:
                unused.append(raw_key)

    # Pass 2 — discover .ditto/ directories not touched this session.
    # Catches stale snapshots from test files that were deleted or renamed.
    if do_prune or session_tracker.records:
        for ditto_dir in rootdir.rglob(".ditto"):
            if not ditto_dir.is_dir():
                continue
            if ditto_dir.resolve() in registered_fs_roots:
                continue
            ghost = LocalMapping(ditto_dir)
            for raw_key in sorted(ghost):
                if do_prune:
                    del ghost[raw_key]
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
