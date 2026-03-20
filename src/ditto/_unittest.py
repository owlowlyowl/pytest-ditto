import inspect
import unittest
from functools import cached_property
from pathlib import Path

from ditto import Snapshot


__all__ = ("DittoTestCase",)


class DittoTestCase(unittest.TestCase):

    # cached_property rather than property: constructs the Snapshot once per test
    # instance and stores it on the instance dict. unittest creates a fresh instance
    # per test method, so the cache is naturally scoped to one test — no teardown
    # needed. Without caching, each access to self.snapshot would create a new
    # Snapshot, discarding the instance between calls within the same test.
    @cached_property
    def snapshot(self) -> Snapshot:
        # inspect.getfile(type(self)) returns the source file of the concrete test
        # class — deterministic regardless of how or where snapshot is accessed.
        path = Path(inspect.getfile(type(self))).parent / ".ditto"
        path.mkdir(exist_ok=True)

        return Snapshot(
            path=path,
            group_name=".".join(self.id().split(".")[-3:]),
        )
