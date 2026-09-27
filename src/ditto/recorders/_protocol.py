from dataclasses import dataclass
from typing import Callable, Generic, TypeVar


__all__ = ("Recorder",)


T = TypeVar("T")


@dataclass(frozen=True)
class Recorder(Generic[T]):
    """
    Recorder: a pair of functions that serialise a value to bytes and back.

    A `Recorder` specifies how a snapshot value becomes the bytes a backend
    stores, and how those bytes become a value again. The bytes are the
    snapshot file's contents: a JSON recorder produces ordinary JSON text, a
    parquet recorder an ordinary parquet file. The type parameter `T`
    constrains the data type this recorder operates on. Use `Recorder[Any]` for
    generic formats (yaml, json). Use a concrete type for format-specific
    recorders (e.g. `Recorder[pd.DataFrame]`).

    A recorder's persisted identifier, which ends its snapshot filenames and is
    recorded in `ditto.lock`, is the name it is registered under (e.g. "yaml",
    "pandas.parquet"), not a property of the recorder.

    Snapshots are handled whole: the value and its serialised bytes must fit in
    memory together. For a library that can only read and write files, wrap its
    functions with `recorder_from_files`.

    Parameters
    ----------
    dumps : Callable[[T], bytes]
        Function that serialises a value of type `T` to bytes.
    loads : Callable[[bytes], T]
        Function that deserialises bytes produced by `dumps` into a value of
        type `T`.
    """

    dumps: Callable[[T], bytes]
    loads: Callable[[bytes], T]
