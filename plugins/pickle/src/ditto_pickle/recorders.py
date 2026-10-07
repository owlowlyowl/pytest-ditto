"""The pickle recorder.

Loading pickle data can execute arbitrary code. Only load snapshots you trust.
"""

import pickle as _pickle
from typing import Any

from ditto.recorders import Recorder


__all__ = ("pickle",)


def _dumps(data: Any) -> bytes:
    return _pickle.dumps(data)


def _loads(raw: bytes) -> Any:
    return _pickle.loads(raw)


pickle: Recorder[Any] = Recorder(dumps=_dumps, loads=_loads)
