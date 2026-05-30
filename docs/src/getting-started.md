# Getting Started

## Installation

Install `pytest-ditto` from PyPI:

```bash
pip install pytest-ditto
```

For optional recorder plugins:

```bash
pip install pytest-ditto[pandas]    # pandas DataFrame recorders
pip install pytest-ditto[pyarrow]   # PyArrow Table recorders
```

## Your First Snapshot Test

Create a test file `test_example.py`:

```python
import ditto


def fn(x: int) -> int:
    return x + 1


def test_fn(snapshot) -> None:
    x = 1
    result = fn(x)
    assert result == snapshot(result, key="fn")
```

Run it:

```bash
pytest test_example.py
```

**First run:** The `snapshot` fixture records `result` to a `.ditto/` directory
next to your test file. The test passes.

**Subsequent runs:** The stored value is loaded and compared. If `fn` changes
its behaviour, the assertion fails.

## Updating Snapshots

When you intentionally change behaviour, regenerate snapshots:

```bash
ditto update
```

Or target specific tests:

```bash
ditto update tests/ -k test_fn
```

## Choosing a Recorder

By default, snapshots are persisted using `pickle`. Use marks to select a
different format:

```python
import ditto


@ditto.yaml
def test_with_yaml(snapshot):
    data = {"name": "pytest-ditto", "version": 1}
    assert data == snapshot(data, key="meta")


@ditto.json
def test_with_json(snapshot):
    data = {"name": "pytest-ditto", "version": 1}
    assert data == snapshot(data, key="meta")
```

The built-in recorders are:

| Mark | Format | File Extension |
|------|--------|---------------|
| `@ditto.pickle` | pickle | `.pkl` |
| `@ditto.yaml` | YAML | `.yaml` |
| `@ditto.json` | JSON | `.json` |

## What's Next?

- [Snapshot Fixture](guides/snapshot-fixture.md) — detailed fixture behaviour
- [Recorders](guides/recorders.md) — all built-in and plugin recorders
- [Storage Backends](guides/backends.md) — store snapshots on S3, in databases, etc.
- [CLI Reference](cli/index.md) — manage snapshots from the command line
