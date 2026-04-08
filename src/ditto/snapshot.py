from __future__ import annotations

import warnings
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .exceptions import DuplicateSnapshotKeyError
from .recorders import Recorder, default as _default_recorder


__all__ = ("Snapshot", "SnapshotKey", "session_tracker")


# ---------------------------------------------------------------------------
# SnapshotKey
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotKey:
    """Fully-qualified identity for a single snapshot value.

    Parameters
    ----------
    module : str
        Rootdir-relative test file stem, e.g. ``"tests/bar/test_api"``.
        Provides namespace isolation across files in shared backends.
    group_name : str
        Test function name, e.g. ``"test_something"``.
    key : str
        Per-snapshot identifier within the test.
    extension : str
        Recorder file extension, e.g. ``"pkl"``, ``"json"``.
    """

    module: str
    group_name: str
    key: str
    extension: str

    @property
    def filename(self) -> str:
        """Short key for filesystem backends: ``'group@key.ext'``.

        Unique within a single ``.ditto/`` directory. The module is implicit
        in the directory path, so on-disk layout is unchanged from pre-backend
        versions of ditto.
        """
        return f"{self.group_name}@{self.key}.{self.extension}"

    def __str__(self) -> str:
        """Namespaced key for remote backends: ``'module/group@key.ext'``.

        Unique across all test files in a shared backend (Redis, S3, etc.).
        """
        return f"{self.module}/{self.group_name}@{self.key}.{self.extension}"


# ---------------------------------------------------------------------------
# Session tracking
# ---------------------------------------------------------------------------


@dataclass
class _BackendRecord:
    backend: MutableMapping[str, bytes]
    key_of: Callable[[SnapshotKey], str]
    accessed: set[SnapshotKey] = field(default_factory=set)


@dataclass
class _SessionTracker:
    """In-memory record of snapshot activity for the current pytest session.

    Reset at ``pytest_sessionstart`` and read at ``pytest_sessionfinish``.
    Never written to disk.
    """

    _records: dict[int, _BackendRecord] = field(default_factory=dict)
    created: list[SnapshotKey] = field(default_factory=list)
    updated: list[SnapshotKey] = field(default_factory=list)
    # Tracks (id(backend), storage_key) — scopes duplicate detection to a single
    # backend instance. Tests using different backends (separate fsspec mappers for
    # different tmp dirs) cannot collide even when group_name and key are identical.
    used_keys: set[tuple[int, str]] = field(default_factory=set)

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
        """Reset per-test state only: duplicate-key detection and created/updated lists.

        Use this between Hypothesis examples to reset duplicate-key tracking without
        discarding the backend access log (_records) that pytest_sessionfinish relies on.
        """
        self.used_keys.clear()
        self.created.clear()
        self.updated.clear()

    def reset(self) -> None:
        self._records.clear()
        self.created.clear()
        self.updated.clear()
        self.used_keys.clear()

    @property
    def records(self) -> dict[int, _BackendRecord]:
        return self._records


session_tracker = _SessionTracker()


# ---------------------------------------------------------------------------
# Key-of free functions
# ---------------------------------------------------------------------------


def _filename_key(sk: SnapshotKey) -> str:
    """Return the short filesystem key for a SnapshotKey (``'group@key.ext'``)."""
    return sk.filename


# ---------------------------------------------------------------------------
# Snapshot dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Snapshot:
    """Immutable configuration for a snapshot: where to store it and how to record it.

    Instances are created by the ``snapshot`` fixture and hold no I/O state.
    All persistence is handled by the module-level free functions
    ``save_snapshot``, ``load_snapshot``, and ``resolve_snapshot``.

    Parameters
    ----------
    group_name : str
        Prefix used in snapshot keys, typically the test name.
    module : str
        Rootdir-relative test file stem (e.g. ``"tests/bar/test_api"``).
        Used to namespace keys in shared backends.
    recorder : Recorder
        Serialisation strategy. Defaults to pickle.
    backend : MutableMapping[str, bytes]
        Storage backend. Defaults to a local fsspec mapper derived from
        ``path`` when ``path`` is provided (backward-compatible construction).
    update : bool
        When True, overwrite existing snapshots. Set by ``--ditto-update``.
    path : Path, optional
        Deprecated. Provide ``backend`` directly instead. When set, a local
        fsspec backend rooted at this path is created automatically and
        ``SnapshotKey.filename`` (short keys) is used for storage.
    """

    group_name: str
    module: str = ""
    recorder: Recorder = field(default_factory=_default_recorder)
    backend: MutableMapping[str, bytes] | None = field(
        default=None, compare=False, hash=False, repr=False
    )
    update: bool = False
    path: Path | None = field(default=None, compare=False, hash=False, repr=False)

    def __post_init__(self) -> None:
        if self.path is not None and self.backend is None:
            from .backends import LocalMapping

            object.__setattr__(self, "backend", LocalMapping(self.path))
        if self.backend is None:
            raise TypeError(
                "Snapshot requires a storage target; provide backend= or path=."
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _key(self, key: str) -> SnapshotKey:
        return SnapshotKey(self.module, self.group_name, key, self.recorder.extension)

    def _key_of(self) -> Callable[[SnapshotKey], str]:
        # Filesystem-local backends (constructed via path=) use the short filename
        # key so existing .ditto/ layouts are preserved unchanged.
        # All other backends use the fully-namespaced str form.
        return _filename_key if self.path is not None else str

    def _store(self) -> Any:
        from .backends import TransformMapping, _make_recorder_transform

        if self.backend is None:
            raise TypeError(
                "Snapshot has no backend configured; "
                "provide path= or backend= at construction."
            )
        return TransformMapping(mapping=self.backend) | _make_recorder_transform(
            self.recorder
        )

    # ------------------------------------------------------------------
    # Deprecated API (Phase 1 — removed in Phase 2)
    # ------------------------------------------------------------------

    def filepath(self, key: str) -> Path:
        """Deprecated. Will be removed in the next release.

        Returns the filesystem path for a snapshot key. Only available for
        filesystem backends (those constructed with ``path=``).
        """
        warnings.warn(
            "Snapshot.filepath() is deprecated and will be removed in the next release."
            " Call snapshot(data, key=key) directly instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        sk = self._key(key)
        if self.path is not None:
            return self.path / sk.filename
        raise TypeError(
            "Snapshot.filepath() is only available for path-based snapshots."
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def __call__(self, data: Any, key: str) -> Any:
        """Save or load the snapshot for ``key``.

        Delegates to ``resolve_snapshot``: saves ``data`` on first call and
        returns the stored value on subsequent calls.
        """
        return resolve_snapshot(self, data, key)


# ---------------------------------------------------------------------------
# Module-level I/O functions
# ---------------------------------------------------------------------------


def save_snapshot(snapshot: Snapshot, data: Any, key: str) -> None:
    """Persist ``data`` to the backend as the snapshot for ``key``."""
    sk = snapshot._key(key)
    storage_key = snapshot._key_of()(sk)
    snapshot._store()[storage_key] = data


def load_snapshot(snapshot: Snapshot, key: str) -> Any:
    """Load and return the stored snapshot value for ``key``.

    Raises
    ------
    FileNotFoundError
        When no snapshot exists for ``key``.
    """
    sk = snapshot._key(key)
    storage_key = snapshot._key_of()(sk)
    try:
        return snapshot._store()[storage_key]
    except KeyError:
        raise FileNotFoundError(
            f"No snapshot file found for key {key!r} (storage key: {storage_key!r})"
        )


def resolve_snapshot(snapshot: Snapshot, data: Any, key: str) -> Any:
    """Return the snapshot value for ``key``, saving it first if absent.

    When ``snapshot.update`` is True, always overwrites the existing value.

    Raises
    ------
    DuplicateSnapshotKeyError
        When the same ``key`` is used more than once within a test.
    """
    sk = snapshot._key(key)
    key_of = snapshot._key_of()
    storage_key = key_of(sk)

    backend = snapshot.backend
    if backend is None:
        raise TypeError(
            "Snapshot has no backend configured; "
            "provide path= or backend= at construction."
        )
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
