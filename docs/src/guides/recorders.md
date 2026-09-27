# Recorders

Recorders determine how snapshot data is serialised and persisted. Each
recorder is a pair of `dumps` and `loads` functions, which convert between a
value and the snapshot file's bytes. The name a recorder is registered under is
its persisted identifier, used as the snapshot file suffix.

## Built-in Recorders

pytest-ditto ships two built-in recorders:

| Mark | Registry Key | Identifier | Best For |
|------|-------------|-----------|----------|
| no mark / `@ditto.json` | `json` | `.json` | Strict, reviewable data (default) |
| `@ditto.yaml` | `yaml` | `.yaml` | Human-readable config, dicts |

### Strict JSON (default)

```python
def test_api_response(snapshot):
    result = {"status": "ok", "data": [1, 2, 3]}
    assert result == snapshot(result, key="result")
```

No mark is needed. The accepted data model is recursively composed of only
these exact built-in types:

- `None`
- `bool`
- `int`
- finite `float`
- `str`
- `list`
- `dict` with exact built-in `str` keys and accepted values

Scalar and container subclasses are rejected. So are non-finite floats,
tuples, sets, frozen sets, bytes-like values, non-string mapping keys,
`Decimal`, `Fraction`, dates, UUIDs, paths, enums, NumPy/pandas/PyArrow values,
dataclasses, named tuples, arbitrary user classes, and cyclic containers.
Errors identify the first invalid path and occur before snapshot persistence.

New files are deterministic UTF-8: object keys are sorted at every depth,
non-ASCII text is literal, indentation is two spaces, line endings are `\n`, and
there is exactly one trailing newline. Loading rejects invalid UTF-8, duplicate
object keys, `NaN`, `Infinity`, `-Infinity`, and numeric overflow. Compact valid
JSON from older releases remains readable and is reformatted only when updated.

### YAML

```python
import ditto


@ditto.yaml
def test_config(snapshot):
    config = {"host": "localhost", "port": 8080}
    assert config == snapshot(config, key="config")
```

## Plugin Recorders

Additional recorders are available via plugin packages. Install the package,
then select its registered convenience mark or use
`@ditto.record("registry_name")`. Recorder packages are ordinary trusted Python
plugins and execute package code when imported.

### Pickle (`pytest-ditto-pickle`)

Users who explicitly need pickle can install its external recorder:

```bash
pip install pytest-ditto-pickle
```

Then select it explicitly with `@ditto.pickle` or
`@ditto.record("pickle")`. Loading pickle data can execute arbitrary code; only
load snapshots you trust. Pickle implementation and policy are owned by that
external distribution, not pytest-ditto core.

### pandas (`pytest-ditto-pandas`)

```bash
pip install pytest-ditto[pandas]
```

| Mark | Registry Key | Identifier |
|------|-------------|-----------|
| `@ditto.pandas.parquet` | `pandas.parquet` | `.pandas.parquet` |
| `@ditto.pandas.json` | `pandas.json` | `.pandas.json` |
| `@ditto.pandas.csv` | `pandas.csv` | `.pandas.csv` |

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

| Mark | Registry Key | Identifier |
|------|-------------|-----------|
| `@ditto.pyarrow.parquet` | `pyarrow.parquet` | `.pyarrow.parquet` |
| `@ditto.pyarrow.feather` | `pyarrow.feather` | `.pyarrow.feather` |
| `@ditto.pyarrow.csv` | `pyarrow.csv` | `.pyarrow.csv` |

```python
import pyarrow as pa
import ditto


@ditto.pyarrow.parquet
def test_table(snapshot):
    table = pa.table({"x": [1, 2, 3]})
    result = process(table)
    assert result.equals(snapshot(result, key="processed"))
```

### Polars (`pytest-ditto-polars`)

```bash
pip install pytest-ditto[polars]
```

| Mark | Registry Key | Identifier |
|------|-------------|-----------|
| `@ditto.polars.parquet` | `polars.parquet` | `.polars.parquet` |
| `@ditto.polars.ipc` | `polars.ipc` | `.polars.ipc` |
| `@ditto.polars.csv` | `polars.csv` | `.polars.csv` |
| `@ditto.polars.ndjson` | `polars.ndjson` | `.polars.ndjson` |

```python
import polars as pl
import polars.testing
import ditto


@ditto.polars.parquet
def test_dataframe(snapshot):
    df = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    result = transform(df)
    pl.testing.assert_frame_equal(result, snapshot(result, key="transformed"))
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
| Strict reviewable Python data | `json` (default) |
| Human-readable diffs in version control | `json` or `yaml` |
| Values outside strict JSON | An explicitly installed suitable recorder |
| pandas DataFrames with type fidelity | `pandas.parquet` |
| Polars DataFrames with type fidelity | `polars.parquet` |
| Large datasets, fast I/O | `parquet` variants |
| Interop with other tools | `json` or `csv` |
