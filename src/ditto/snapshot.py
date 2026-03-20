from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ditto.io._pickle import Pickle
from ditto.io._protocol import Base


__all__ = ("Snapshot",)


@dataclass(frozen=True)
class Snapshot:
    """
    Immutable configuration for a snapshot: where to store it and how to serialise it.

    Instances are created by the `snapshot` fixture and hold no I/O state.
    All persistence operations are handled by the module-level free functions
    `save_snapshot`, `load_snapshot`, and `resolve_snapshot`.

    Attributes
    ----------
    path : Path
        Directory in which snapshot files are stored.
    group_name : str
        Prefix used in snapshot filenames, typically the test name.
    io : type[Base]
        IO handler class responsible for serialisation. Defaults to `Pickle`.
    """

    path: Path
    group_name: str
    io: type[Base] = Pickle

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
        return self.path / f"{stem}.{self.io.extension}"

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
    snapshot.io.save(data, snapshot.filepath(key))


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
    return snapshot.io.load(snapshot.filepath(key))


def resolve_snapshot(snapshot: Snapshot, data: Any, key: str) -> Any:
    """
    Return the snapshot value for `key`, saving it first if it does not yet exist.

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
        `data` on first call; the previously stored value on subsequent calls.
    """
    if snapshot.filepath(key).exists():
        return load_snapshot(snapshot, key)
    save_snapshot(snapshot, data, key)
    return data
