from __future__ import annotations

from collections.abc import Hashable, MutableMapping
from contextlib import AbstractContextManager, ExitStack
from dataclasses import dataclass, field
from typing import cast

import pytest

from ditto.snapshot import _SessionTracker


__all__ = (
    "TargetCacheKey",
    "DittoSession",
    "SESSION_STATE",
    "session_state",
    "maybe_enter",
    "fail_session",
)


TargetCacheKey = tuple[str, Hashable]


# Held on `config.stash`, never at module level: an in-process `pytester` run
# executes a nested pytest session inside the same interpreter, with this same
# package as its plugin. Module-level state would be shared between the two
# sessions, leaking the nested run's snapshots into the outer `ditto.lock` and
# wiping the outer run's observations (#115).


@dataclass
class DittoSession:
    """ditto's mutable state for one pytest session."""

    tracker: _SessionTracker = field(default_factory=_SessionTracker)
    exit_stack: ExitStack = field(default_factory=ExitStack)
    entered_backends: dict[int, MutableMapping[str, bytes]] = field(
        default_factory=dict
    )
    backend_cache: dict[TargetCacheKey, MutableMapping[str, bytes]] = field(
        default_factory=dict
    )
    introspect_backends: dict[str, MutableMapping[str, bytes]] = field(
        default_factory=dict
    )


SESSION_STATE = pytest.StashKey[DittoSession]()


def session_state(config: pytest.Config) -> DittoSession:
    """Return this config's session state, creating it on first use."""
    state = config.stash.get(SESSION_STATE, None)
    if state is None:
        state = config.stash[SESSION_STATE] = DittoSession()
    return state


def maybe_enter(
    backend: MutableMapping[str, bytes], state: DittoSession
) -> MutableMapping[str, bytes]:
    """Enter a context-manager backend into the session `ExitStack` exactly once.

    Returns the value of `__enter__` (typically `self`). No-op for backends that
    are not context managers and for backends already entered.
    """
    bid = id(backend)
    if bid in state.entered_backends:
        return state.entered_backends[bid]
    if isinstance(backend, AbstractContextManager):
        entered = cast(
            MutableMapping[str, bytes],
            state.exit_stack.enter_context(backend),
        )
        state.entered_backends[bid] = entered
        return entered
    return backend


def fail_session(session: pytest.Session) -> None:
    """Mark the pytest session as failed without masking a real test failure."""
    if session.exitstatus == 0:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
