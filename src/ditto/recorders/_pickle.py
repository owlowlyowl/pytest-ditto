import pickle as _pickle
from pathlib import Path
from typing import Any

from ._protocol import Recorder


__all__ = ("pickle",)


def _save(data: Any, filepath: Path) -> None:
    with open(filepath, "wb") as f:
        _pickle.dump(data, f)


def _load(filepath: Path) -> Any:
    with open(filepath, "rb") as f:
        return _pickle.load(f)


pickle = Recorder(extension="pkl", save=_save, load=_load)
