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

Only parquet round-trips a DataFrame exactly. JSON and CSV change some values or
types on the way through, and a snapshot comparison then fails even though the
code under test didn't change.

| Format | Index | Values and dtypes |
|--------|-------|-------------------|
| parquet | preserved | preserved |
| json | preserved, except an index named `index` | preserved, except numeric widths |
| csv | single-level only; values re-parsed | re-parsed from text |

**JSON** (`to_json(orient="table")`):

- An index named `index` is read back unnamed, and pandas warns that the name is
  not round-trippable.
- Numeric columns are widened to 64 bits, so `int8`, `int32` and `uint16` come
  back as `int64`, and `float32` as `float64`.

**CSV** keeps no type information, so every column and the index are parsed
from text on load:

- Strings that look like numbers become numbers: `"001"` is read back as `1`.
- Strings pandas treats as missing, such as `"NA"`, `"null"` and `""`, become
  `NaN`.
- dtypes are inferred again, so `int32` comes back as `int64`, and categoricals
  come back as plain strings.
- Only a single-level index is supported. `DatetimeIndex`, `PeriodIndex`,
  `CategoricalIndex` and `MultiIndex` are not.
- A `RangeIndex` may come back as a plain integer index, depending on the pandas
  version. Pass `check_index_type=False` to `pd.testing.assert_frame_equal` to
  allow for that. It does not help with any of the changed values above.

Use `@ditto.pandas.parquet` for DataFrames that hit any of these cases.
