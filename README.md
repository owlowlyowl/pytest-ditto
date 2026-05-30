# pytest-ditto

[![PyPI version](https://badge.fury.io/py/pytest-ditto.svg)](https://badge.fury.io/py/pytest-ditto)
[![Continuous Integration](https://github.com/owlowlyowl/pytest-ditto/actions/workflows/ci.yml/badge.svg)](https://github.com/owlowlyowl/pytest-ditto/actions/workflows/ci.yml)
[![Documentation](https://github.com/owlowlyowl/pytest-ditto/actions/workflows/docs.yml/badge.svg)](https://owlowlyowl.github.io/pytest-ditto/)

Snapshot testing pytest plugin with minimal ceremony and flexible recorders.

**[📖 Documentation](https://owlowlyowl.github.io/pytest-ditto/)**

## Features

- **Snapshot fixture** — record test outputs once, assert they don't change
- **Flexible recorders** — built-in pickle, YAML, JSON; plugin recorders for pandas and PyArrow
- **Remote backends** — store snapshots locally, on S3, in PostgreSQL, Redis, DuckDB, or anywhere via fsspec
- **Named profiles** — reusable, named backend targets with isolated credentials
- **CLI tools** — list, update, prune, lint, and manage snapshots from the command line
- **unittest support** — `DittoTestCase` for `unittest.TestCase`-based tests

## Quick Start

```bash
pip install pytest-ditto
```

```python
import ditto


def fn(x: int) -> int:
    return x + 1


def test_fn(snapshot) -> None:
    result = fn(1)
    assert result == snapshot(result, key="fn")
```

First run records the result. Subsequent runs assert it hasn't changed.

## Recorders

| Mark | Format | Extension |
|------|--------|-----------|
| `@ditto.pickle` | pickle (default) | `.pkl` |
| `@ditto.yaml` | YAML | `.yaml` |
| `@ditto.json` | JSON | `.json` |
| `@ditto.pandas.parquet` | pandas DataFrame | `.pandas.parquet` |
| `@ditto.pyarrow.parquet` | PyArrow Table | `.pyarrow.parquet` |

## Documentation

Full documentation is available at **[owlowlyowl.github.io/pytest-ditto](https://owlowlyowl.github.io/pytest-ditto/)**, including:

- [Getting Started](https://owlowlyowl.github.io/pytest-ditto/getting-started/)
- [Guides](https://owlowlyowl.github.io/pytest-ditto/guides/snapshot-fixture/) (recorders, backends, custom plugins)
- [CLI Reference](https://owlowlyowl.github.io/pytest-ditto/cli/)
- [API Reference](https://owlowlyowl.github.io/pytest-ditto/reference/)

## Examples

See [examples/](examples/README.md) for self-contained local, PostgreSQL, Redis, and DuckDB examples.
