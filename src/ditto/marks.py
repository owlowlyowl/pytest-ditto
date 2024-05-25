import sys

import pytest

from ditto.io._plugins import MARK_REGISTRY


__all__ = [
    "record",
    "yaml",
    "json",
    "pickle",
    *MARK_REGISTRY.keys(),
]

# Base mark for ditto package.
record = pytest.mark.record

# Explicit IO based marks.
yaml = record("yaml")
json = record("json")
pickle = record("pkl")

    
def _load_plugin_marks() -> None:
    for name, marks in MARK_REGISTRY.items():
        setattr(sys.modules[__name__], name, marks)


_load_plugin_marks()
