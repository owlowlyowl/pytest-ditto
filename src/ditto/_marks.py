import pytest


__all__ = ("record", "yaml", "json")

record = pytest.mark.record
"""Mark a test's snapshots with a recorder, and optionally a target.

Use as `@ditto.record("yaml")`, `@ditto.record("json", target=uri)` or
`@ditto.record("json", target_profile=name)`. The recorder name is required.
A test may have one `record` mark, set on its function, class or module.
"""

yaml = record("yaml")
"""Store a test's snapshots as YAML: `@ditto.record("yaml")`."""

json = record("json")
"""Store a test's snapshots as strict JSON, the default: `@ditto.record("json")`."""
