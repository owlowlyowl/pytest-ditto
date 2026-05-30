# pytest-ditto

Snapshot testing with minimal ceremony and flexible recorders.

<div class="grid cards" markdown>

- :material-camera: **Snapshot Testing**

    Record test outputs once, assert they don't change. No boilerplate.

- :material-swap-horizontal: **Flexible Recorders**

    Built-in pickle, YAML, and JSON. Plugin recorders for pandas, PyArrow, and more.

- :material-cloud-upload: **Remote Backends**

    Store snapshots locally, on S3, in PostgreSQL, Redis, DuckDB — anywhere.

- :material-console: **CLI Tools**

    Manage snapshots from the command line: list, update, prune, lint, and more.

</div>

## Quick Example

```python
import ditto


def fn(x: int) -> int:
    return x + 1


def test_fn(snapshot) -> None:
    result = fn(1)
    assert result == snapshot(result, key="fn")
```

The first run records the result. Subsequent runs assert it hasn't changed.

## How It Works

1. **Request the `snapshot` fixture** in your test function
2. **Call `snapshot(value, key="name")`** — the value is persisted on first run
3. **Assert equality** — subsequent runs compare against the stored snapshot
4. **Choose a recorder** — use `@ditto.yaml`, `@ditto.json`, or any registered format

```python
import ditto


@ditto.yaml
def test_config(snapshot):
    config = load_config()
    assert config == snapshot(config, key="config")
```

## Installation

```bash
pip install pytest-ditto
```

With optional recorder plugins:

```bash
pip install pytest-ditto[pandas]    # pandas DataFrames
pip install pytest-ditto[pyarrow]   # PyArrow Tables
```

[Get Started](getting-started.md){ .md-button .md-button--primary }
[CLI Reference](cli/index.md){ .md-button }
