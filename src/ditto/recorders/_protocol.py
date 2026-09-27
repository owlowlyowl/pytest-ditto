from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Generic, TypeVar


__all__ = ("Recorder",)


T = TypeVar("T")


@dataclass(frozen=True)
class Recorder(Generic[T]):
    """
    Recorder: a pair of save and load functions.

    A `Recorder` specifies how snapshot data is written to and read from disk.
    The type parameter `T` constrains the data type this recorder operates on.
    Use `Recorder[Any]` for generic formats (yaml, json).
    Use a concrete type for format-specific recorders (e.g. `Recorder[pd.DataFrame]`).

    A recorder's persisted identifier, which ends its snapshot filenames and is
    recorded in `ditto.lock`, is the name it is registered under (e.g. "yaml",
    "pandas.parquet"), not a property of the recorder.

    Parameters
    ----------
    save : Callable[[T, Path], None]
        Function that persists a value of type `T` to the given path.
    load : Callable[[Path], T]
        Function that reads and returns a value of type `T` from the given path.
    """

    save: Callable[[T, Path], None]
    load: Callable[[Path], T]
