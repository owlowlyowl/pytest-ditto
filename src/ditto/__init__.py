from ditto._version import __version__ as version
from ditto.snapshot import Snapshot
from ditto._unittest import DittoTestCase
from ditto import marks
# Using wildcard import as marks has an __all__. Still feels dirty...
from ditto.marks import *


__all__ = [
    "version",
    "Snapshot",
    "DittoTestCase",
    *marks.__all__,
]