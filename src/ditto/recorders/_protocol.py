from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Generic, TypeVar


__all__ = ("Recorder",)


T = TypeVar("T")


@dataclass(frozen=True)
class Recorder(Generic[T]):
    """
    Recorder: an extension string paired with save and load functions.

    A `Recorder` specifies how snapshot data is written to and read from disk.
    The type parameter `T` constrains the data type this recorder operates on.
    Use `Recorder[Any]` for generic formats (pickle, yaml, json).
    Use a concrete type for format-specific recorders (e.g. `Recorder[pd.DataFrame]`).

    Parameters
    ----------
    extension : str
        File extension used for snapshot files (e.g. "pkl", "json").
    save : Callable[[T, Path], None]
        Function that persists a value of type `T` to the given path.
    load : Callable[[Path], T]
        Function that reads and returns a value of type `T` from the given path.
    """

    extension: str
    save: Callable[[T, Path], None]
    load: Callable[[Path], T]
