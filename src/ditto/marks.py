import sys
from types import SimpleNamespace
from dataclasses import dataclass

import pytest

from ditto.io._plugins import MARK_REGISTRY


__all__ = [
    "record",
    "yaml",
    "json",
    "pickle",
    "pandas",
    *MARK_REGISTRY.keys(),
]

# Base mark for ditto package.
record = pytest.mark.record

# Explicit IO based marks.
yaml = record("yaml")
json = record("json")
pickle = record("pkl")

# Explicit library specific marks with multiple output formats.
@dataclass(frozen=True)
class PandasMarks:
    parquet: pytest.MarkDecorator
    json: pytest.MarkDecorator


pandas = PandasMarks(
    parquet=record("pandas_parquet"),
    json=record("pandas_json"),
)


# def _load_marks() -> SimpleNamespace:
#     return SimpleNamespace(**MARK_REGISTRY)

    
def _load_plugin_marks() -> None:
    for name, marks in MARK_REGISTRY.items():
        print(name, marks)
        setattr(sys.modules[__name__], name, marks)


_load_plugin_marks()
