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

Install a plugin to snapshot other kinds of data. Each one registers its own
recorders and marks; `ditto recorders` lists everything installed. Plugins are
ordinary Python packages and run their code when imported, so install only ones
you trust.

| Plugin | Install | Records | Marks |
|--------|---------|---------|-------|
| [pandas](../plugins/pandas.md) | `pip install "pytest-ditto[pandas]"` | DataFrames and Series | `@ditto.pandas.parquet`, `.json`, `.csv` |
| [polars](../plugins/polars.md) | `pip install "pytest-ditto[polars]"` | DataFrames | `@ditto.polars.parquet`, `.ipc`, `.csv`, `.ndjson` |
| [PyArrow](../plugins/pyarrow.md) | `pip install "pytest-ditto[pyarrow]"` | Tables | `@ditto.pyarrow.parquet`, `.feather`, `.csv` |
| [pickle](../plugins/pickle.md) | `pip install pytest-ditto-pickle` | Any picklable value | `@ditto.pickle` |

```python
import pandas as pd
import ditto


@ditto.pandas.parquet
def test_dataframe(snapshot):
    result = transform(pd.DataFrame({"a": [1, 2, 3]}))
    pd.testing.assert_frame_equal(result, snapshot(result, key="transformed"))
```

Text formats such as JSON and CSV are easy to review, but most change some
data on the way through: they round floats, re-infer types or drop metadata.
Each plugin's page lists what its formats keep. Prefer the parquet recorders
unless you need to read a snapshot as text.

!!! danger "Loading pickle data can execute arbitrary code"
    Only load pickle snapshots you trust. See [pickle](../plugins/pickle.md).

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
| pandas DataFrames or Series | `pandas.parquet` |
| Polars DataFrames | `polars.parquet` |
| PyArrow Tables | `pyarrow.parquet` |
| Large datasets, fast I/O | `parquet` variants |
| Interop with other tools | `json` or `csv` |
