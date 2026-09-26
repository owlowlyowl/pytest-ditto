"""The pickle recorder.

Loading pickle data can execute arbitrary code. Only load snapshots you trust.
"""

import pickle as _pickle
from pathlib import Path
from typing import Any

from ditto.recorders import Recorder


__all__ = ("pickle",)


def _save(data: Any, filepath: Path) -> None:
    with open(filepath, "wb") as f:
        _pickle.dump(data, f)


def _load(filepath: Path) -> Any:
    with open(filepath, "rb") as f:
        return _pickle.load(f)


# The identifier is `pkl`, not the recorder's name, `pickle`: it is the file
# extension pytest-ditto 1.x used, so 1.x snapshots keep loading.
pickle: Recorder[Any] = Recorder(identifier="pkl", save=_save, load=_load)
