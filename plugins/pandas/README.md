# pytest-ditto-pandas

Extension plugin for [`pytest-ditto`](https://github.com/owlowlyowl/pytest-ditto) for `pandas` DataFrame snapshots.

Use the following marks for their associated recorder:
- `@ditto.pandas.parquet`
- `@ditto.pandas.json`
- `@ditto.pandas.csv`

Each mark is shorthand for `@ditto.record("pandas.<format>")`.

## Installation
```bash
pip install pytest-ditto[pandas]
```

## Usage

```python
import pandas as pd

import ditto


def awesome_fn_to_test(df: pd.DataFrame):
    df.loc[:, "a"] *= 2
    return df


# The following test uses pandas.DataFrame.to_parquet to write the data snapshot to the
# `.ditto` directory with filename:
# `<module>.test_fn_with_parquet_dataframe_snapshot@ab_dataframe.pandas.parquet`.


@ditto.pandas.parquet
def test_fn_with_parquet_dataframe_snapshot(snapshot):
    input_data = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 9]})
    result = awesome_fn_to_test(input_data)
    pd.testing.assert_frame_equal(result, snapshot(result, key="ab_dataframe"))


# The following test uses pandas.DataFrame.to_json(orient="table") to write the data
# snapshot to the `.ditto` directory with filename:
# `<module>.test_fn_with_json_dataframe_snapshot@ab_dataframe.pandas.json`.


@ditto.pandas.json
def test_fn_with_json_dataframe_snapshot(snapshot):
    input_data = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 9]})
    result = awesome_fn_to_test(input_data)
    pd.testing.assert_frame_equal(result, snapshot(result, key="ab_dataframe"))
```

### Format notes

| Format | Index preserved | dtype preserved |
|--------|----------------|-----------------|
| parquet | yes | yes |
| json | yes | yes |
| csv | single-level numeric or string only (see below) | no |

The CSV recorder does not preserve index type metadata. Supported index types
for round-trip are single-level numeric (note: `RangeIndex` is read back as
`Int64`) and string. `DatetimeIndex`, `PeriodIndex`, `CategoricalIndex`, and
`MultiIndex` are not supported — use `@ditto.pandas.parquet` or
`@ditto.pandas.json` for DataFrames with these index types.

When comparing a CSV snapshot with `pd.testing.assert_frame_equal`, pass
`check_index_type=False` to account for the `RangeIndex` → `Int64` conversion.
