import unittest
import inspect
from typing import ClassVar
from pathlib import Path

from ditto import Snapshot


def _calling_test_path() -> Path:
    frame = inspect.currentframe()
    outer_frames = inspect.getouterframes(frame)
    # 2 calls back up the stack, index 1 of the frame has the calling filepath
    return Path(outer_frames[2][1]).parent


class DittoTestCase(unittest.TestCase):

    record: ClassVar[bool] = True

    @property
    def snapshot(self) -> Snapshot:
        path = _calling_test_path() / ".ditto"
        path.mkdir(exist_ok=True)

        return Snapshot(
            path=path,
            group_name=".".join(self.id().split(".")[-3:]),
        )
