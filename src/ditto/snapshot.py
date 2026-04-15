from __future__ import annotations

from collections.abc import Callable, MutableMapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from .exceptions import DuplicateSnapshotKeyError
from .recorders import Recorder, default as _default_recorder


__all__ = ("Snapshot", "SnapshotKey", "session_tracker")


@dataclass(frozen=True)
class SnapshotKey:
    """Fully-qualified identity for a single snapshot value.

    Parameters
    ----------
    module : str
        Rootdir-relative test file stem, e.g. "tests/bar/test_api".
        Provides namespace isolation across files in shared backends.
    group_name : str
        Test function name, e.g. "test_something". For class-based tests includes
        the class prefix: "TestClass.test_something".
    key : str
        Per-snapshot identifier within the test.
    extension : str
        Recorder file extension, e.g. "pkl", "json".
    """

    module: str
    group_name: str
    key: str
    extension: str

    @property
    def filename(self) -> str:
        """Short key: 'group@key.ext'. Not used as the storage key for any backend.

        Kept for reference and user code that inspects `SnapshotKey` objects.
        File backends use `_flat_key` ('module.group@key.ext') and remote backends
        use `str(key)` ('module/group@key.ext').
        """
        return f"{self.group_name}@{self.key}.{self.extension}"

    def __str__(self) -> str:
        """Namespaced key for remote backends: 'module/group@key.ext'.

        Unique across all test files in a shared backend (Redis, S3, etc.).
        Also used as the human-readable display name in session reports.
        """
        return f"{self.module}/{self.group_name}@{self.key}.{self.extension}"

    @property
    def display_name(self) -> str:
        """Human-readable label for the session report: 'module/group@key.ext'."""
        return str(self)


@dataclass
class _BackendRecord:
    backend: MutableMapping[str, bytes]
    key_of: Callable[[SnapshotKey], str]
    accessed: set[SnapshotKey] = field(default_factory=set)


@dataclass
class _SessionTracker:
    """In-memory record of snapshot activity for the current pytest session.

    Reset at `pytest_sessionstart` and read at `pytest_sessionfinish`.
    Never written to disk.
    """

    _records: dict[int, _BackendRecord] = field(default_factory=dict)
    created: list[SnapshotKey] = field(default_factory=list)
    updated: list[SnapshotKey] = field(default_factory=list)
    # Tracks (id(backend), storage_key) — scopes duplicate detection to a single
    # backend instance. Tests using different backends (separate fsspec mappers for
    # different tmp dirs) cannot collide even when group_name and key are identical.
    used_keys: set[tuple[int, str]] = field(default_factory=set)
    # Maps id(backend) → set of module stems that used this backend this session.
    # Populated by the snapshot fixture at fixture-creation time (before any calls),
    # so modules that request snapshot but make no calls are still tracked. Used by
    # Pass 1 prune to restrict enumeration to owned key prefixes only.
    backend_modules: dict[int, set[str]] = field(default_factory=dict)

    def register_backend_module(self, backend_id: int, module: str) -> None:
        """Record that `module` uses the backend identified by `backend_id`.

        Called by the `snapshot` fixture at fixture-creation time so that Pass 1
        prune knows which key prefixes are owned by this session's collected tests.
        """
        self.backend_modules.setdefault(backend_id, set()).add(module)

    def register_access(
        self,
        backend: MutableMapping[str, bytes],
        key_of: Callable[[SnapshotKey], str],
        key: SnapshotKey,
    ) -> None:
        backend_id = id(backend)
        if backend_id not in self._records:
            self._records[backend_id] = _BackendRecord(backend=backend, key_of=key_of)
        self._records[backend_id].accessed.add(key)

    def reset_keys(self) -> None:
        """Reset per-example duplicate-key detection only.

        Safe to call between Hypothesis examples. Does not touch the
        session-level `created` and `updated` lists, which accumulate
        across the entire session and are read by `render_session_report`
        at the end. Those are only cleared in `reset()`.
        """
        self.used_keys.clear()

    def reset(self) -> None:
        self._records.clear()
        self.created.clear()
        self.updated.clear()
        self.used_keys.clear()
        self.backend_modules.clear()

    @property
    def records(self) -> dict[int, _BackendRecord]:
        return self._records


session_tracker = _SessionTracker()
"""Module-level singleton that tracks snapshot activity for the current pytest session.

Collects created, updated, and accessed snapshot keys across all tests.
Reset at `pytest_sessionstart` and consumed at `pytest_sessionfinish`
to produce the session report.

Notes
-----
`reset()` is called by the plugin at `pytest_sessionstart` to clear state
from any previous session. Between Hypothesis examples, `reset_keys()`
clears per-example duplicate-key detection without touching the session-level
`created` and `updated` lists.
"""


def _flat_key(sk: SnapshotKey) -> str:
    """Flat filesystem key for file backends: 'module.group@key.ext'.

    Slashes in the module path are replaced with dots so the key maps to
    a single flat filename — no subdirectories inside `.ditto/`.
    Unique across all test files sharing the same `file://` target.
    """
    module_dotted = sk.module.replace("/", ".")
    return f"{module_dotted}.{sk.group_name}@{sk.key}.{sk.extension}"


@dataclass(frozen=True)
class Snapshot:
    """Immutable configuration for a snapshot: where to store it and how to record it.

    Instances are created by the `snapshot` fixture and hold no I/O state.
    All persistence is handled by the module-level free functions
    `save_snapshot`, `load_snapshot`, and `resolve_snapshot`.

    Parameters
    ----------
    group_name : str
        Prefix used in snapshot keys. Derived from the pytest nodeid minus the
        file path (e.g. "test_something" or "TestClass.test_something").
    module : str
        Rootdir-relative test file stem (e.g. "tests/bar/test_api"). Required
        for all backends. Provides namespace isolation across test files.
    target : str
        URI identifying the storage location. The scheme controls key format:
        `file://` uses flat dotted keys (`module.group@key.ext`);
        all other schemes use slash-separated keys (`module/group@key.ext`).
        Always use absolute `file://` URIs (e.g. `file:///home/user/proj/tests/.ditto`).
    _backend : MutableMapping[str, bytes]
        Resolved storage backend. Conventionally private — set by the fixture via
        `_resolve_target`. Use `target=` to communicate where data goes.
    recorder : Recorder
        Serialisation strategy. Defaults to pickle.
    update : bool
        When True, overwrite existing snapshots. Set by `--ditto-update`.
    """

    group_name: str
    module: str
    target: str
    _backend: MutableMapping[str, bytes] = field(repr=False, compare=False, hash=False)
    recorder: Recorder = field(default_factory=_default_recorder)
    update: bool = False

    def __post_init__(self) -> None:
        if not self.module:
            raise TypeError(
                "Snapshot requires module= for all backends. "
                "Pass the rootdir-relative test file stem, e.g. "
                "module='tests/my_module/test_foo'."
            )

    def _key(self, key: str) -> SnapshotKey:
        return SnapshotKey(self.module, self.group_name, key, self.recorder.extension)

    def _key_of(self) -> Callable[[SnapshotKey], str]:
        # file:// backends use a flat dotted key (module.group@key.ext) so .ditto/
        # stays a flat directory. All other backends use slash-namespaced keys.
        return _flat_key if urlparse(self.target).scheme == "file" else str

    def _store(self) -> Any:
        from .backends import TransformMapping, _make_recorder_transform

        return TransformMapping(mapping=self._backend) | _make_recorder_transform(
            self.recorder
        )

    def __call__(self, data: Any, key: str) -> Any:
        """Save or load the snapshot for `key`.

        Delegates to `resolve_snapshot`: saves `data` on first call and
        returns the stored value on subsequent calls.
        """
        return resolve_snapshot(self, data, key)


def save_snapshot(snapshot: Snapshot, data: Any, key: str) -> None:
    """Persist `data` to the backend as the snapshot for `key`."""
    sk = snapshot._key(key)
    storage_key = snapshot._key_of()(sk)
    snapshot._store()[storage_key] = data


def load_snapshot(snapshot: Snapshot, key: str) -> Any:
    """Load and return the stored snapshot value for `key`.

    Raises
    ------
    FileNotFoundError
        When no snapshot exists for `key`.
    """
    sk = snapshot._key(key)
    storage_key = snapshot._key_of()(sk)
    store = snapshot._store()
    if storage_key not in store:
        raise FileNotFoundError(
            f"No snapshot file found for key {key!r} (storage key: {storage_key!r})"
        )
    return store[storage_key]


def resolve_snapshot(snapshot: Snapshot, data: Any, key: str) -> Any:
    """Return the snapshot value for `key`, saving it first if absent.

    When `snapshot.update` is True, always overwrites the existing value.

    Raises
    ------
    DuplicateSnapshotKeyError
        When the same `key` is used more than once within a test.
    """
    sk = snapshot._key(key)
    key_of = snapshot._key_of()
    storage_key = key_of(sk)

    backend = snapshot._backend
    used_key = (id(backend), storage_key)
    if used_key in session_tracker.used_keys:
        raise DuplicateSnapshotKeyError(key)
    session_tracker.used_keys.add(used_key)
    session_tracker.register_access(backend, key_of, sk)

    store = snapshot._store()
    exists = storage_key in store

    if not exists or snapshot.update:
        store[storage_key] = data
        (
            session_tracker.updated
            if (snapshot.update and exists)
            else session_tracker.created
        ).append(sk)
        return data
    return store[storage_key]
