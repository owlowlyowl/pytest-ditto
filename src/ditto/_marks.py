import pytest


__all__ = ("record", "yaml", "json")

# Base mark for ditto package.
record = pytest.mark.record

# Convenience marks — each wraps record() with the IO type name pre-applied.
yaml = record("yaml")
json = record("json")
