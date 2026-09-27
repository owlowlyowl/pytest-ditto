import json
from pathlib import Path
from typing import Any

from ditto.recorders import Recorder, recorder_from_files


def _dumps(value: Any) -> bytes:
    return json.dumps(value).encode("utf-8")


def _loads(raw: bytes) -> Any:
    return json.loads(raw.decode("utf-8"))


def _save(value: Any, path: Path) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# One recorder serialises in memory, the other through the file adapter, so the
# installed-wheel smoke test exercises both.
recorder = Recorder(dumps=_dumps, loads=_loads)
dotted = recorder_from_files(save=_save, load=_load, suffix=".json")
