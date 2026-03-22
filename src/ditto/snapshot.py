from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .recorders import Recorder, default as _default_recorder


__all__ = ("Snapshot", "session_tracker")


@dataclass
class _SessionTracker:
    """
    In-memory record of snapshot activity for the current pytest session.

    Reset at `pytest_sessionstart` and read at `pytest_sessionfinish`.
    Never written to disk.
    """

    accessed: set[Path] = field(default_factory=set)
    created: list[Path] = field(default_factory=list)
    updated: list[Path] = field(default_factory=list)

    def reset(self) -> None:
        self.accessed.clear()
        self.created.clear()
        self.updated.clear()


session_tracker = _SessionTracker()


@dataclass(frozen=True)
class Snapshot:
    """
    Immutable configuration for a snapshot: where to store it and how to record it.

    Instances are created by the `snapshot` fixture and hold no I/O state.
    All persistence operations are handled by the module-level free functions
    `save_snapshot`, `load_snapshot`, and `resolve_snapshot`.

    Attributes
    ----------
    path : Path
        Directory in which snapshot files are stored.
    group_name : str
        Prefix used in snapshot filenames, typically the test name.
    recorder : Recorder
        Recorder instance responsible for serialisation. Defaults to `pickle`.
    update : bool
        When True, overwrite existing snapshot files with new values.
        Set by the `--ditto-update` pytest flag. Defaults to False.
    """

    path: Path
    group_name: str
    recorder: Recorder = field(default_factory=_default_recorder)
    update: bool = False

    def filepath(self, key: str) -> Path:
        """
        Return the file path for the snapshot identified by `key`.

        Parameters
        ----------
        key : str
            Unique identifier for this snapshot within the test.

        Returns
        -------
        Path
            Full path to the snapshot file.
        """
        stem = f"{self.group_name}@{key}"
        return self.path / f"{stem}.{self.recorder.extension}"

    def __call__(self, data: Any, key: str) -> Any:
        """
        Save or load the snapshot for `key`.

        Delegates to `resolve_snapshot`: saves `data` on first call and returns
        the stored value on subsequent calls.

        Parameters
        ----------
        data : Any
            The value to snapshot.
        key : str
            Unique identifier for this snapshot within the test.

        Returns
        -------
        Any
            `data` on first call; the previously stored value on subsequent calls.
        """
        return resolve_snapshot(self, data, key)


def save_snapshot(snapshot: Snapshot, data: Any, key: str) -> None:
    """
    Persist `data` to disk as the snapshot for `key`.

    Parameters
    ----------
    snapshot : Snapshot
        The snapshot configuration.
    data : Any
        The value to persist.
    key : str
        Unique identifier for this snapshot within the test.
    """
    snapshot.path.mkdir(parents=True, exist_ok=True)
    snapshot.recorder.save(data, snapshot.filepath(key))


def load_snapshot(snapshot: Snapshot, key: str) -> Any:
    """
    Load and return the stored snapshot value for `key`.

    Parameters
    ----------
    snapshot : Snapshot
        The snapshot configuration.
    key : str
        Unique identifier for this snapshot within the test.

    Returns
    -------
    Any
        The value previously persisted by `save_snapshot`.
    """
    return snapshot.recorder.load(snapshot.filepath(key))


def resolve_snapshot(snapshot: Snapshot, data: Any, key: str) -> Any:
    """
    Return the snapshot value for `key`, saving it first if it does not yet exist.

    When `snapshot.update` is True, always overwrites the existing file.

    Parameters
    ----------
    snapshot : Snapshot
        The snapshot configuration.
    data : Any
        The value to snapshot on first call.
    key : str
        Unique identifier for this snapshot within the test.

    Returns
    -------
    Any
        `data` on first call (or when updating); the previously stored value otherwise.
    """
    fp = snapshot.filepath(key)
    session_tracker.accessed.add(fp)
    if fp.exists() and not snapshot.update:
        return load_snapshot(snapshot, key)
    existed = fp.exists()
    save_snapshot(snapshot, data, key)
    (session_tracker.updated if existed else session_tracker.created).append(fp)
    return data
