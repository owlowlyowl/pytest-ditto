# pytest-ditto

[![PyPI version](https://badge.fury.io/py/pytest-ditto.svg)](https://badge.fury.io/py/pytest-ditto)
[![Continuous Integration](https://github.com/owlowlyowl/pytest-ditto/actions/workflows/ci.yml/badge.svg)](https://github.com/owlowlyowl/pytest-ditto/actions/workflows/ci.yml)
[![Documentation](https://github.com/owlowlyowl/pytest-ditto/actions/workflows/docs.yml/badge.svg)](https://owlowlyowl.github.io/pytest-ditto/)

Snapshot regression testing for dataframe transformations in pytest, with
minimal ceremony, pluggable recorders, and local or remote storage backends.

**[📖 Documentation](https://owlowlyowl.github.io/pytest-ditto/)**

## Features

- **Snapshot fixture**: record a test's output once, then fail when it changes
- **Recorders**: strict JSON by default, built-in YAML, and plugins for pandas,
  polars, PyArrow and pickle
- **Storage backends**: keep snapshots next to your tests, on S3 or anywhere
  fsspec reaches, or in your own backend for a database such as Redis
- **Lock file**: a committed `ditto.lock` records every snapshot, so CI fails on
  missing or stale ones
- **CLI**: update, verify, prune, list and inspect snapshots

## Quick Start

```bash
pip install pytest-ditto
```

<!-- test: passes -->
```python
def summarise(prices):
    return {"count": len(prices), "total": sum(prices)}


def test_summarise(snapshot):
    result = summarise([3, 4.5])
    assert result == snapshot(result, key="summary")
```

The first run stores the result as a snapshot. Every later run compares the
result with it, and fails if it has changed. Run `ditto verify` in CI so a
missing snapshot fails instead of being recorded again.

Upgrading from 1.x? Read
[Upgrading to 2.0](https://owlowlyowl.github.io/pytest-ditto/upgrading/) first:
2.0 doesn't find snapshots recorded by 1.x.

## Documentation

Full documentation is at
**[owlowlyowl.github.io/pytest-ditto](https://owlowlyowl.github.io/pytest-ditto/)**:

- [Getting Started](https://owlowlyowl.github.io/pytest-ditto/getting-started/)
- [Recorders](https://owlowlyowl.github.io/pytest-ditto/guides/recorders/)
- [Running in CI](https://owlowlyowl.github.io/pytest-ditto/guides/ci/)
- [Configuration](https://owlowlyowl.github.io/pytest-ditto/reference/configuration/)
- [CLI Reference](https://owlowlyowl.github.io/pytest-ditto/cli/)

## Examples

See [examples/](https://github.com/owlowlyowl/pytest-ditto/tree/main/examples)
for self-contained local, PostgreSQL, Redis and DuckDB backends.
