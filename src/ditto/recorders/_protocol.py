from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Generic, TypeVar


__all__ = ("Recorder",)


T = TypeVar("T")


@dataclass(frozen=True)
class Recorder(Generic[T]):
    """
    Recorder: a persisted identifier string paired with save and load functions.

    A `Recorder` specifies how snapshot data is written to and read from disk.
    The type parameter `T` constrains the data type this recorder operates on.
    Use `Recorder[Any]` for generic formats (pickle, yaml, json).
    Use a concrete type for format-specific recorders (e.g. `Recorder[pd.DataFrame]`).

    Notes
    -----
    The field name `extension` is historical. Its current contract is broader than
    a pure terminal file extension: it is the canonical persisted recorder
    identifier appended to snapshot keys. Built-in recorders use short values such
    as `pkl` and `json`; optional plugin recorders may use dotted identifiers such
    as `pandas.parquet` or `pyarrow.csv`.

    Parameters
    ----------
    extension : str
        Canonical persisted recorder identifier appended to snapshot names (e.g.
        "pkl", "json", "pandas.parquet"). This value may contain dots and is
        not guaranteed to match the mark alias or recorder registry key.
    save : Callable[[T, Path], None]
        Function that persists a value of type `T` to the given path.
    load : Callable[[Path], T]
        Function that reads and returns a value of type `T` from the given path.
    """

    extension: str
    save: Callable[[T, Path], None]
    load: Callable[[Path], T]
