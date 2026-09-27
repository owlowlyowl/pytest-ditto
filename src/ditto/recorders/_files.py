from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypeVar

from ._protocol import Recorder


__all__ = ("recorder_from_files",)


T = TypeVar("T")


def recorder_from_files(
    *,
    save: Callable[[T, Path], None],
    load: Callable[[Path], T],
    suffix: str,
) -> Recorder[T]:
    """
    Adapt a library that reads and writes files to the byte-based `Recorder`.

    Each `dumps` and `loads` call uses a fresh temporary directory holding one
    file, `snapshot<suffix>`, which is removed afterwards whether the call
    succeeds or fails. Libraries that can serialise to bytes directly should
    build a `Recorder` from their in-memory functions instead, avoiding the
    file I/O.

    Only single-file formats are supported. A value returned by `load` must not
    depend on the temporary file after `load` returns, so lazy or memory-mapped
    readers are unsuitable.

    Parameters
    ----------
    save : Callable[[T, Path], None]
        Function that writes a value to the given path.
    load : Callable[[Path], T]
        Function that reads a value from the given path.
    suffix : str
        Filename suffix the library expects, e.g. `".parquet"`. It names only
        the temporary file; the snapshot's filename comes from the name the
        recorder is registered under.

    Returns
    -------
    Recorder[T]
        A recorder whose `dumps` and `loads` go through a temporary file.

    Raises
    ------
    ValueError
        If `suffix` does not start with `.`, is only `.`, or contains a path
        separator.
    """
    if not suffix.startswith(".") or suffix == "." or "/" in suffix or "\\" in suffix:
        raise ValueError(
            f"suffix must be a filename suffix such as '.parquet', got {suffix!r}"
        )

    def dumps(value: T) -> bytes:
        with TemporaryDirectory() as directory:
            path = Path(directory) / f"snapshot{suffix}"
            save(value, path)
            return path.read_bytes()

    def loads(raw: bytes) -> T:
        with TemporaryDirectory() as directory:
            path = Path(directory) / f"snapshot{suffix}"
            path.write_bytes(raw)
            return load(path)

    return Recorder(dumps=dumps, loads=loads)
