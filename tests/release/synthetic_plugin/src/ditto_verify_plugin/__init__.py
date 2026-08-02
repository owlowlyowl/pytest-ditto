import json
from pathlib import Path
from typing import Any

import pytest

from ditto.recorders import Recorder


def _save(value: Any, path: Path) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


recorder = Recorder(extension="synthetic", save=_save, load=_load)


def mark():
    return pytest.mark.record("synthetic")
