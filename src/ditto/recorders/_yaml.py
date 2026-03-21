import yaml as _yaml
from pathlib import Path
from typing import Any

from ._protocol import Recorder


__all__ = ("yaml",)


def _save(data: Any, filepath: Path) -> None:
    with open(filepath, "w") as f:
        _yaml.dump(data, f, Dumper=_yaml.SafeDumper)


def _load(filepath: Path) -> Any:
    with open(filepath, "r") as f:
        return _yaml.load(f, Loader=_yaml.SafeLoader)


yaml = Recorder(extension="yaml", save=_save, load=_load)
