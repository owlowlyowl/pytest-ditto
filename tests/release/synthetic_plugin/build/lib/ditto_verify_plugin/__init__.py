import json
from pathlib import Path
from typing import Any

from ditto.recorders import Recorder


def _save(value: Any, path: Path) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


recorder = Recorder(identifier="synthetic", save=_save, load=_load)
dotted = Recorder(identifier="verify.dotted", save=_save, load=_load)
