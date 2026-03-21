import json as _json
from pathlib import Path
from typing import Any

from ._protocol import Recorder


__all__ = ("json",)


def _save(data: Any, filepath: Path) -> None:
    with open(filepath, "w") as f:
        _json.dump(data, f)


def _load(filepath: Path) -> Any:
    with open(filepath, "r") as f:
        return _json.load(f)


json = Recorder(extension="json", save=_save, load=_load)
