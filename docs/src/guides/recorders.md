# Recorders

Recorders determine how snapshot data is serialised and persisted. Each
recorder is a pair of `save` and `load` functions plus a file extension.

## Built-in Recorders

pytest-ditto ships three built-in recorders:

| Mark | Registry Key | Extension | Best For |
|------|-------------|-----------|----------|
| `@ditto.pickle` | `pickle` | `.pkl` | Any Python object (default) |
| `@ditto.yaml` | `yaml` | `.yaml` | Human-readable config, dicts |
| `@ditto.json` | `json` | `.json` | JSON-serialisable data |

### pickle (default)

```python
def test_anything(snapshot):
    result = complex_computation()
    assert result == snapshot(result, key="result")
```

No mark needed — pickle is the default recorder. Handles any picklable object.

### YAML

```python
import ditto


@ditto.yaml
def test_config(snapshot):
    config = {"host": "localhost", "port": 8080}
    assert config == snapshot(config, key="config")
```

### JSON

```python
import ditto


@ditto.json
def test_api_response(snapshot):
    response = {"status": "ok", "data": [1, 2, 3]}
    assert response == snapshot(response, key="response")
```

## Plugin Recorders

Additional recorders are available via plugin packages:

### pandas (`pytest-ditto-pandas`)

```bash
pip install pytest-ditto[pandas]
```

| Mark | Registry Key | Extension |
|------|-------------|-----------|
| `@ditto.pandas.parquet` | `pandas_parquet` | `.pandas.parquet` |
| `@ditto.pandas.json` | `pandas_json` | `.pandas.json` |
| `@ditto.pandas.csv` | `pandas_csv` | `.pandas.csv` |

```python
import pandas as pd
import ditto


@ditto.pandas.parquet
def test_dataframe(snapshot):
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    result = transform(df)
    pd.testing.assert_frame_equal(result, snapshot(result, key="transformed"))
```

### PyArrow (`pytest-ditto-pyarrow`)

```bash
pip install pytest-ditto[pyarrow]
```

| Mark | Registry Key | Extension |
|------|-------------|-----------|
| `@ditto.pyarrow.parquet` | `pyarrow_parquet` | `.pyarrow.parquet` |
| `@ditto.pyarrow.feather` | `pyarrow_feather` | `.pyarrow.feather` |
| `@ditto.pyarrow.csv` | `pyarrow_csv` | `.pyarrow.csv` |

```python
import pyarrow as pa
import ditto


@ditto.pyarrow.parquet
def test_table(snapshot):
    table = pa.table({"x": [1, 2, 3]})
    result = process(table)
    assert result.equals(snapshot(result, key="processed"))
```

## The Generic `@ditto.record()` Mark

All convenience marks are shorthands for `@ditto.record("name")`:

```python
import ditto

# These are equivalent:
@ditto.yaml
def test_a(snapshot): ...

@ditto.record("yaml")
def test_b(snapshot): ...
```

Use `@ditto.record("name")` to reference any registered recorder by its
registry key, including custom ones.

## Choosing a Recorder

| Consideration | Recommended |
|---------------|-------------|
| Any Python object | `pickle` (default) |
| Human-readable diffs in version control | `yaml` or `json` |
| pandas DataFrames with type fidelity | `pandas.parquet` |
| Large datasets, fast I/O | `parquet` variants |
| Interop with other tools | `json` or `csv` |
