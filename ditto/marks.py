from types import SimpleNamespace

import pytest


__all__ = [
    "record",
    "yaml",
    "json",
    "pickle",
    "pandas",
]

# Base mark for ditto package.
record = pytest.mark.record

# Explicit IO based marks.
yaml = record("yaml")
json = record("json")
pickle = record("pkl")

# Explicit library specific marks with multiple output formats.
pandas = SimpleNamespace(
    parquet=record("pandas_parquet"),
    # json=record("pandas_json"),
)
