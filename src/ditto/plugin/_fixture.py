from __future__ import annotations

from urllib.parse import urlparse

import pytest

from ditto.snapshot import Snapshot
from ditto._lockfile import portable_target_id, split_nodeid

from ._options import run_options
from ._selection import parse_mark_target_selection, resolve_recorder
from ._session import session_state
from ._targets import is_checkout_local, resolve_target


__all__ = ("snapshot",)


@pytest.fixture
def snapshot(request: pytest.FixtureRequest) -> Snapshot:
    rootdir = request.config.rootpath
    if not request.path.is_relative_to(rootdir):
        # pytest gives such a test a node id without its file path, so it has
        # no module to key its snapshots by.
        raise ValueError(
            f"ditto: {request.path} is outside the rootdir {rootdir}; snapshot "
            "tests must live under the rootdir."
        )
    # Derive the identity from the node id exactly as the lock does, so the
    # keys written here are the keys lock, verify and prune expect.
    module, group_name = split_nodeid(request.node.nodeid)
    marks = list(request.node.iter_markers(name="record"))
    recorder_name, recorder = resolve_recorder(marks)
    options = run_options(request.config)

    mark_target, mark_profile = parse_mark_target_selection(marks)
    backend, abs_uri = resolve_target(mark_target, mark_profile, request)

    target_id = portable_target_id(abs_uri, rootdir)
    state = session_state(request.config)
    state.tracker.register_backend_module(id(backend), module)
    state.tracker.register_target_backend(target_id, urlparse(abs_uri).scheme, backend)
    if is_checkout_local(abs_uri, rootdir):
        state.checkout_local_targets.add(target_id)

    if options.introspect_path:
        state.introspect_backends.setdefault(abs_uri, backend)

    return Snapshot(
        module=module,
        group_name=group_name,
        target=abs_uri,
        _backend=backend,
        recorder=recorder,
        recorder_name=recorder_name,
        mode=options.snapshot_mode,
        nodeid=request.node.nodeid,
        target_id=target_id,
        _tracker=state.tracker,
    )
