from types import SimpleNamespace

import pytest

from ditto._version import __version__ as version
from ditto.snapshot import Snapshot
from ditto._unittest import DittoTestCase

record = pytest.mark.record

yaml = record("yaml")
json = record("json")
pickle = record("pkl")

pandas = SimpleNamespace(
    parquet=record("pandas_parquet"),
)
