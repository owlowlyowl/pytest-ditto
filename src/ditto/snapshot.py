from __future__ import annotations

import hashlib
import json
import string
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from .exceptions import (
    DittoSnapshotNameCollisionError,
    DittoSnapshotNameTooLongError,
    DuplicateSnapshotKeyError,
)
from .recorders import Recorder, default as _default_recorder


__all__ = ("LockSeen", "Snapshot", "SnapshotKey", "SnapshotMode")


# The name of the recorder unmarked tests use.
DEFAULT_RECORDER_NAME = "json"

# Stands in for a `Snapshot` recorder or recorder name that was not passed.
_UNSET: Any = object()


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
    identifier : str
        Recorder identifier, e.g. "json", "yaml", "pandas.parquet".
    nodeid : str
        Full pytest node id of the owning test, exactly as pytest reports it,
        or "" for a `Snapshot` built outside the fixture. `module` and
        `group_name` are derived from it and lose detail (the file extension,
        `::` inside a parametrize ID), so the stored name's hash uses the node
        id when there is one.
    """

    module: str
    group_name: str
    key: str
    identifier: str
    nodeid: str = ""

    @property
    def filename(self) -> str:
        """Short key: 'group@key.ext'. Not used as the storage key for any backend.

        Kept for reference and user code that inspects `SnapshotKey` objects.
        File backends store a snapshot under `_flat_key` and remote backends
        under `_remote_key`.
        """
        return f"{self.group_name}@{self.key}.{self.identifier}"

    def __str__(self) -> str:
        """Readable identity: 'module/group@key.ext'.

        Shown in session reports. Not a storage key: stored names replace
        unsafe characters and add a hash (see `_flat_key`).
        """
        return f"{self.module}/{self.group_name}@{self.key}.{self.identifier}"

    @property
    def display_name(self) -> str:
        """Human-readable label for the session report: 'module/group@key.ext'."""
        return str(self)


@dataclass(frozen=True)
class LockSeen:
    """A lock entry observed this session, plus where it lives.

    Parameters
    ----------
    target_id : str
        Portable lock-file target id (rootdir-relative for `file://`, URI otherwise).
    scheme : str
        The target's URI scheme, e.g. `file` or `s3`. Used to derive the storage
        key for this entry later.
    nodeid : str
        Full pytest node id for the owning test, e.g. `tests/test_api.py::test_foo`.
    key : str
        Per-snapshot identifier within the test.
    recorder : str
        Recorder identifier, e.g. `json`, `yaml`, `pandas.parquet`.
    """

    target_id: str
    scheme: str
    nodeid: str
    key: str
    recorder: str


@dataclass(frozen=True)
class WrittenSnapshot:
    """One snapshot this session wrote, and the target it was written to.

    The session report groups these by `target_id` and names each by the test,
    key and recorder the `SnapshotKey` carries, which is what `ditto list` shows.
    """

    target_id: str
    key: SnapshotKey
    recorder: str


@dataclass(frozen=True)
class _RegisteredTarget:
    """A target the session used: where it is, and the backend built for it."""

    canonical_uri: str
    scheme: str
    backend: MutableMapping[str, bytes]


@dataclass
class _BackendRecord:
    backend: MutableMapping[str, bytes]
    key_of: Callable[[SnapshotKey], str]
    accessed: set[SnapshotKey] = field(default_factory=set)


@dataclass
class _SessionTracker:
    """In-memory record of snapshot activity for one pytest session.

    The plugin creates one per session (on `config.stash`) and reads it at
    `pytest_sessionfinish`. A `Snapshot` built outside the fixture gets its own.
    Never written to disk.
    """

    _records: dict[int, _BackendRecord] = field(default_factory=dict)
    created: list[WrittenSnapshot] = field(default_factory=list)
    updated: list[WrittenSnapshot] = field(default_factory=list)
    # Maps (id(backend), storage_key) to the snapshot stored under it. Scoping to
    # a backend instance means tests using different backends (separate fsspec
    # mappers for different tmp dirs) cannot collide even when group_name and key
    # are identical; keeping the snapshot tells a reused key from two different
    # snapshots whose names collide.
    used_keys: dict[tuple[int, str], SnapshotKey] = field(default_factory=dict)
    # Maps id(backend) → set of module stems that used this backend this session.
    # Populated by the snapshot fixture at fixture-creation time (before any calls),
    # so modules that request snapshot but make no calls are still tracked. Used by
    # Pass 1 prune to restrict enumeration to owned key prefixes only.
    backend_modules: dict[int, set[str]] = field(default_factory=dict)
    lock_created: set[LockSeen] = field(default_factory=set)
    lock_accessed: set[LockSeen] = field(default_factory=set)
    # Maps portable target_id → the target registered for it; populated at
    # fixture creation so verify (and prune) can enumerate every active target.
    target_backends: dict[str, _RegisteredTarget] = field(default_factory=dict)

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

    def register_target_backend(
        self,
        target_id: str,
        canonical_uri: str,
        backend: MutableMapping[str, bytes],
    ) -> None:
        """Record the canonical URI and live backend resolved for `target_id`."""
        self.target_backends[target_id] = _RegisteredTarget(
            canonical_uri, urlparse(canonical_uri).scheme, backend
        )

    def record_lock_seen(self, seen: LockSeen, *, created: bool) -> None:
        """Record a lock entry accessed this session; also as created on first write."""
        self.lock_accessed.add(seen)
        if created:
            self.lock_created.add(seen)

    @property
    def records(self) -> dict[int, _BackendRecord]:
        return self._records


# Characters a snapshot name's label keeps; every other character becomes "_".
# ASCII only, so no platform forbids them in file names and macOS's Unicode
# normalisation of file names can't apply. "@" separates the label's two parts
# and "~" starts the hash, so neither appears within a part.
_LABEL_SAFE = frozenset(string.ascii_letters + string.digits + "._-[]=,+")
# The most the label keeps of the group name and key, for readability.
_LABEL_GROUP_MAX = 80
_LABEL_KEY_MAX = 40
# Hex characters of the identity hash kept in a name: 64 bits. Two names only
# rely on the hash when their labels match, and an accidental collision then
# needs billions of snapshots with one label.
_HASH_LENGTH = 16
# The longest file name most file systems allow, in bytes.
_NAME_MAX_BYTES = 255
# The fewest label characters (both parts and their "@") a name must keep.
_LABEL_MIN = 16


def _label_part(text: str, limit: int) -> str:
    return "".join(c if c in _LABEL_SAFE else "_" for c in text)[:limit]


def _identity_hash(sk: SnapshotKey) -> str:
    """The first hex characters of the SHA-256 of the snapshot's exact identity.

    The identity is `[test, key, identifier]`, where `test` is the node id, or
    `module::group_name` for a snapshot without one. It is serialised as a
    compact JSON array (`ensure_ascii=False`, UTF-8), so no field's content can
    be mistaken for a boundary between fields. This is part of the stored
    format: changing it renames every snapshot.
    """
    test = sk.nodeid or f"{sk.module}::{sk.group_name}"
    identity = json.dumps(
        [test, sk.key, sk.identifier], ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:_HASH_LENGTH]


def _label(sk: SnapshotKey, room: int | None = None) -> str:
    """The readable 'group@key' part of a name.

    Characters outside `_LABEL_SAFE` become `_`. The group name keeps at most
    `_LABEL_GROUP_MAX` characters and the key `_LABEL_KEY_MAX`. Given `room`,
    the label is shortened further to at most that many characters, the group
    name giving way first, to half the space.
    """
    group = _label_part(sk.group_name, _LABEL_GROUP_MAX)
    key = _label_part(sk.key, _LABEL_KEY_MAX)
    if room is not None:
        room -= len("@")
        group = group[: max(room - len(key), room // 2)]
        key = key[: room - len(group)]
    return f"{group}@{key}"


def _snapshot_name(sk: SnapshotKey, label_room: int | None = None) -> str:
    """The part of a storage key after the module: 'label~hash.ext'.

    The label (see `_label`) is for people to read and isn't decoded;
    `ditto.lock` records the exact identity. The hash tells apart snapshots
    whose labels match, such as parametrize IDs that differ only in case or in
    characters the label replaces.
    """
    return f"{_label(sk, label_room)}~{_identity_hash(sk)}.{sk.identifier}"


def _flat_key(sk: SnapshotKey) -> str:
    """Storage key for file backends: 'module.label~hash.ext'.

    Slashes in the module path are replaced with dots so the key maps to
    a single flat filename — no subdirectories inside `.ditto/`. The label is
    shortened so the whole name fits in `_NAME_MAX_BYTES`.

    Raises
    ------
    DittoSnapshotNameTooLongError
        When the module path leaves fewer than `_LABEL_MIN` label characters.
    """
    prefix = sk.module.replace("/", ".") + "."
    fixed = len(prefix.encode("utf-8")) + len(f"~{'0' * _HASH_LENGTH}.")
    room = _NAME_MAX_BYTES - fixed - len(sk.identifier)
    if room < _LABEL_MIN:
        raise DittoSnapshotNameTooLongError(sk.module, _NAME_MAX_BYTES)
    return f"{prefix}{_snapshot_name(sk, room)}"


def _remote_key(sk: SnapshotKey) -> str:
    """Storage key for all other backends: 'module/label~hash.ext'.

    A remote key isn't a file name, so its label isn't shortened to fit one:
    the module path can be as long as the test file's path.
    """
    return f"{sk.module}/{_snapshot_name(sk)}"


class SnapshotMode(Enum):
    """How `resolve_snapshot` treats the stored value for a key.

    Attributes
    ----------
    RECORD
        Save the value when the key is absent; otherwise return the stored value.
    UPDATE
        Always save the value, overwriting a stored one. Set by `--ditto-update`.
    VERIFY
        Never write: return the stored value, or the given value when the key is
        absent. Set by `--ditto-verify`, so a verify run cannot recreate a
        deleted snapshot.

    A value that is saved, or returned under VERIFY for an absent key, is
    serialised and deserialised first, and the deserialised value is returned.
    """

    RECORD = "record"
    UPDATE = "update"
    VERIFY = "verify"


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
        Serialisation strategy. Defaults to strict JSON.
    recorder_name : str
        The recorder's registered name, which is its persisted identifier: it
        ends snapshot filenames and is recorded in `ditto.lock`. The fixture
        passes the name the recorder was selected by. A directly constructed
        `Snapshot` passes `recorder` and `recorder_name` together, or neither
        for strict JSON (`"json"`). The name may be omitted with the strict JSON
        recorder itself, whose name is `"json"`.
    mode : SnapshotMode
        Whether a snapshot is recorded, updated, or only verified. Defaults to
        `SnapshotMode.RECORD`.
    nodeid : str
        Full pytest node id for the owning test, e.g. `tests/test_api.py::test_foo`.
        Used to build lock-file entries. Empty when constructed outside the fixture.
    target_id : str
        Portable lock-file target id (rootdir-relative for `file://`, URI otherwise).
    _tracker : _SessionTracker
        Where snapshot activity is recorded. The fixture passes its pytest
        session's tracker; a directly constructed `Snapshot` gets a private one.
    """

    group_name: str
    module: str
    target: str
    _backend: MutableMapping[str, bytes] = field(repr=False, compare=False, hash=False)
    recorder: Recorder = _UNSET
    recorder_name: str = _UNSET
    mode: SnapshotMode = SnapshotMode.RECORD
    nodeid: str = ""
    target_id: str = ""
    _tracker: _SessionTracker = field(
        default_factory=_SessionTracker, repr=False, compare=False, hash=False
    )

    def __post_init__(self) -> None:
        if not self.module:
            raise TypeError(
                "Snapshot requires module= for all backends. "
                "Pass the rootdir-relative test file stem, e.g. "
                "module='tests/my_module/test_foo'."
            )
        if not isinstance(self.mode, SnapshotMode):
            raise TypeError(
                f"mode must be a SnapshotMode, got {self.mode!r}. "
                "Use SnapshotMode.UPDATE in place of update=True and "
                "SnapshotMode.VERIFY in place of readonly=True."
            )
        recorder, name = self.recorder, self.recorder_name
        if name is _UNSET:
            if recorder is _UNSET:
                recorder = _default_recorder()
            elif recorder is not _default_recorder():
                raise TypeError(
                    "Snapshot requires recorder_name= with recorder=. Pass the "
                    "name the recorder is registered under, e.g. "
                    "recorder_name='yaml'; it names the snapshot files."
                )
            name = DEFAULT_RECORDER_NAME
        elif recorder is _UNSET:
            raise TypeError(
                "Snapshot requires recorder= with recorder_name=. Pass the "
                f"recorder registered as {name!r}, e.g. "
                f"recorder=recorders.get({name!r})."
            )
        object.__setattr__(self, "recorder", recorder)
        object.__setattr__(self, "recorder_name", name)

    def _key(self, key: str) -> SnapshotKey:
        if not isinstance(key, str):
            raise TypeError(f"key must be a str, got {type(key).__name__}")
        return SnapshotKey(
            self.module, self.group_name, key, self.recorder_name, self.nodeid
        )

    def _key_of(self) -> Callable[[SnapshotKey], str]:
        # file:// backends use a flat dotted key so .ditto/ stays a flat
        # directory. All other backends use slash-namespaced keys.
        return _flat_key if urlparse(self.target).scheme == "file" else _remote_key

    def __call__(self, data: Any, key: str) -> Any:
        """Save or load the snapshot for `key`.

        Delegates to `resolve_snapshot`: saves `data` on first call and
        returns the stored value on subsequent calls. Either way the value
        returned is what the recorder reads back, not `data` itself.
        """
        return resolve_snapshot(self, data, key)


def _round_trip(recorder: Recorder, data: Any) -> tuple[bytes, Any]:
    """Serialise `data`, then deserialise those bytes.

    Returns the bytes to store and the value they restore to, so a caller writes
    exactly the bytes it has shown the recorder can read.
    """
    raw = recorder.dumps(data)
    return raw, recorder.loads(raw)


def save_snapshot(snapshot: Snapshot, data: Any, key: str) -> None:
    """Persist `data` to the backend as the snapshot for `key`.

    Nothing is written if the recorder cannot deserialise the bytes it produced.
    """
    sk = snapshot._key(key)
    storage_key = snapshot._key_of()(sk)
    raw, _ = _round_trip(snapshot.recorder, data)
    snapshot._backend[storage_key] = raw


def load_snapshot(snapshot: Snapshot, key: str) -> Any:
    """Load and return the stored snapshot value for `key`.

    Raises
    ------
    FileNotFoundError
        When no snapshot exists for `key`.
    """
    sk = snapshot._key(key)
    storage_key = snapshot._key_of()(sk)
    backend = snapshot._backend
    if storage_key not in backend:
        raise FileNotFoundError(
            f"No snapshot file found for key {key!r} (storage key: {storage_key!r})"
        )
    return snapshot.recorder.loads(backend[storage_key])


def resolve_snapshot(snapshot: Snapshot, data: Any, key: str) -> Any:
    """Return the snapshot value for `key`, first writing `data` if the mode requires.

    How the stored value is treated depends on `snapshot.mode`; see `SnapshotMode`.
    Whenever `data` is returned in place of a stored value, it is first passed
    through the recorder (`dumps`, then `loads`), so the caller's assertion sees
    what a later run would read back.

    Raises
    ------
    DuplicateSnapshotKeyError
        When the same `key` is used more than once within a test.
    DittoSnapshotNameCollisionError
        When another snapshot this session has the same storage key.
    """
    sk = snapshot._key(key)
    key_of = snapshot._key_of()
    storage_key = key_of(sk)

    backend = snapshot._backend
    tracker = snapshot._tracker
    used_key = (id(backend), storage_key)
    previous = tracker.used_keys.get(used_key)
    if previous == sk:
        raise DuplicateSnapshotKeyError(key)
    if previous is not None:
        raise DittoSnapshotNameCollisionError(storage_key, str(previous), str(sk))
    tracker.used_keys[used_key] = sk
    tracker.register_access(backend, key_of, sk)

    recorder = snapshot.recorder
    exists = storage_key in backend

    match snapshot.mode, exists:
        case SnapshotMode.RECORD | SnapshotMode.VERIFY, True:
            value = recorder.loads(backend[storage_key])
        case SnapshotMode.VERIFY, False:
            # Never write to the backend: leave it untouched so the drift check
            # can detect the missing key.
            _, value = _round_trip(recorder, data)
        case _:
            raw, value = _round_trip(recorder, data)
            backend[storage_key] = raw
            written = WrittenSnapshot(
                target_id=snapshot.target_id,
                key=sk,
                recorder=snapshot.recorder_name,
            )
            (tracker.updated if exists else tracker.created).append(written)

    # Recorded only after the write succeeded, so a snapshot that failed to
    # persist leaves no lock entry behind (see #84). A Snapshot built outside the
    # fixture has no target and takes no part in lock maintenance.
    if snapshot.target_id:
        tracker.record_lock_seen(
            LockSeen(
                target_id=snapshot.target_id,
                scheme=urlparse(snapshot.target).scheme,
                nodeid=snapshot.nodeid,
                key=key,
                recorder=snapshot.recorder_name,
            ),
            created=not exists,
        )
    return value
