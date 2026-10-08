# Assertions and recorders

Read this reference when writing snapshot assertions, choosing a recorder, or
diagnosing serialization and comparison failures.

## Built-in data

The unmarked 2.x default is strict JSON. It accepts exact built-in `None`,
`bool`, `int`, finite `float`, `str`, `list`, and string-keyed `dict` values,
recursively. Subclasses, tuples, sets, bytes, dates, decimals, NumPy scalars,
non-finite floats, and arbitrary classes are rejected. Errors identify the first
unsupported path; do not replace meaningful values with strings just to record
them.

```python
def test_summary(snapshot):
    result = {"count": 2, "total": 7.5}
    assert result == snapshot(result, key="summary")
```

`@ditto.json` selects the same recorder explicitly. `@ditto.yaml` selects the
built-in YAML recorder. A readable format does not guarantee type fidelity:
YAML reads a tuple back as a list, for example.

The fixture returns the value read back by the recorder, including when recording
or updating. A comparison that fails on the first run can therefore reveal a
lossy round trip. Updating again cannot repair that loss.

## Tabular data

Use an installed recorder for the data model and its native comparison function.
Prefer parquet when values and types matter, subject to the plugin's documented
limitations. JSON and CSV formats can round values, re-infer types, or lose
metadata. Use them when those tradeoffs fit the tested contract.

| Value | Recorder mark | Assertion |
| --- | --- | --- |
| pandas DataFrame | `@ditto.pandas.parquet` | `pd.testing.assert_frame_equal(actual, expected)` |
| pandas Series | `@ditto.pandas.parquet` | `pd.testing.assert_series_equal(actual, expected)` |
| Polars DataFrame | `@ditto.polars.parquet` | `polars.testing.assert_frame_equal(actual, expected)` |
| PyArrow Table | `@ditto.pyarrow.parquet` | `assert actual.equals(expected)` |

For example, with `pytest-ditto-pandas` installed:

```python
import ditto
import pandas as pd


@ditto.pandas.parquet
def test_prices(snapshot):
    result = pd.DataFrame({"item": ["apple", "pear"], "price": [3.0, 4.5]})
    pd.testing.assert_frame_equal(result, snapshot(result, key="prices"))
```

Do not use a DataFrame's elementwise `==` as a scalar assertion. If exact float
values are part of the contract, explicitly choose the comparator's exactness
or tolerances; its defaults may accept small changes.
For PyArrow, pass `check_metadata=True` to `Table.equals` when schema metadata
is part of the contract; it is ignored by default.

For binary snapshot review, load the old and new bytes using the installed
recorder and inspect the changed values, schema, index, and relevant metadata.
Inspect the existing baseline without overwriting it first. A binary Git diff
alone does not show whether the new behavior is correct.

## Failure decisions

| Observation | Next step |
| --- | --- |
| Existing baseline differs from current output | Establish whether the requested behavior explains the difference before updating. |
| First recording fails comparison | Check serialization round-trip fidelity and comparator behavior. |
| Strict JSON rejects a value | Choose a contract-preserving representation or a suitable installed recorder. |
| A timestamp, random ID, or ordering changes on each run | Control the input or normalize only a field outside the contract. |
| A duplicate snapshot key is reported | Give each call a distinct key within that test. |
| A recorder is unknown or fails to load | Inspect `ditto recorders`; use `ditto doctor` to diagnose installed plugin contracts. |

Do not weaken type checks, drop columns, sort meaningful output, or increase
tolerances solely to obtain a passing comparison.

## Other recorders

`@ditto.record("registered.name")` selects any registered recorder. Install
plugins through the project's dependency workflow when the task requires them.
`ditto recorders` lists registrations from package metadata without importing
plugins; `ditto doctor` imports them to check that they load correctly.

Pickle is an external, explicitly selected recorder in 2.x. Loading pickle can
execute arbitrary code; use it only when deliberately required and its baseline
is trusted. It is not a general fallback for unsupported JSON values.

For custom recorder work, the 2.x contract is `Recorder(dumps=..., loads=...)`:
`dumps` returns bytes and `loads` reads those bytes back. Keep the registered
name stable because it is part of the persisted snapshot identity.

Further details: [recorders](https://owlowlyowl.github.io/pytest-ditto/guides/recorders/)
and [plugin format notes](https://owlowlyowl.github.io/pytest-ditto/plugins/pandas/).
