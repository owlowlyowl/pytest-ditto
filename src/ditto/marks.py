from dataclasses import dataclass

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
@dataclass(frozen=True)
class PandasMarks:
    parquet: pytest.MarkDecorator
    json: pytest.MarkDecorator


pandas = PandasMarks(
    parquet=record("pandas_parquet"),
    json=record("pandas_json"),
)
