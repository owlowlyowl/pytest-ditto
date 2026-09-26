from __future__ import annotations

from urllib.parse import urlparse

import pytest

from ditto.snapshot import Snapshot
from ditto._lockfile import portable_target_id

from ._options import run_options
from ._selection import parse_mark_target_selection, resolve_recorder
from ._session import session_state
from ._targets import resolve_target


__all__ = ("snapshot",)


@pytest.fixture
def snapshot(request: pytest.FixtureRequest) -> Snapshot:
    rootdir = request.config.rootpath
    module = request.path.relative_to(rootdir).with_suffix("").as_posix()
    marks = list(request.node.iter_markers(name="record"))
    recorder = resolve_recorder(marks)
    options = run_options(request.config)

    mark_target, mark_profile = parse_mark_target_selection(marks)
    backend, abs_uri = resolve_target(mark_target, mark_profile, request)

    state = session_state(request.config)
    state.tracker.register_backend_module(id(backend), module)
    state.tracker.register_target_backend(
        portable_target_id(abs_uri, rootdir), urlparse(abs_uri).scheme, backend
    )

    if options.introspect_path:
        state.introspect_backends.setdefault(abs_uri, backend)

    file_prefix = str(request.path.relative_to(rootdir)) + "::"
    qualified_name = request.node.nodeid.removeprefix(file_prefix)
    group_name = qualified_name.replace("::", ".")

    return Snapshot(
        module=module,
        group_name=group_name,
        target=abs_uri,
        _backend=backend,
        recorder=recorder,
        mode=options.snapshot_mode,
        nodeid=request.node.nodeid,
        target_id=portable_target_id(abs_uri, rootdir),
        _tracker=state.tracker,
    )
