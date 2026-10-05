# pytest-ditto-pandas

Extension plugin for [`pytest-ditto`](https://github.com/owlowlyowl/pytest-ditto) for `pandas` DataFrame and Series snapshots.

Use the following marks for their associated recorder:
- `@ditto.pandas.parquet`
- `@ditto.pandas.json`
- `@ditto.pandas.csv`

Each mark is shorthand for `@ditto.record("pandas.<format>")`.

**Use `@ditto.pandas.parquet` unless you need a snapshot you can read as text.**
It's the only format that keeps every dtype and value exactly, though it turns
some non-string column and index names into strings. JSON and CSV are readable,
but they change some data on the way through; see [Format notes](#format-notes).

## Installation
```bash
pip install pytest-ditto[pandas]
```

It needs pandas 2.2 or later and pyarrow 16.1.0 or later.

## Usage

```python
import pandas as pd

import ditto


def awesome_fn_to_test(df: pd.DataFrame):
    df.loc[:, "a"] *= 2
    return df


# The following test uses pandas.DataFrame.to_parquet to write the data snapshot to the
# `.ditto` directory with filename:
# `<module>.test_fn_with_parquet_dataframe_snapshot@ab_dataframe~<hash>.pandas.parquet`.


@ditto.pandas.parquet
def test_fn_with_parquet_dataframe_snapshot(snapshot):
    input_data = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 9]})
    result = awesome_fn_to_test(input_data)
    pd.testing.assert_frame_equal(result, snapshot(result, key="ab_dataframe"))


# The following test uses pandas.DataFrame.to_json(orient="table") to write the data
# snapshot to the `.ditto` directory with filename:
# `<module>.test_fn_with_json_dataframe_snapshot@ab_dataframe~<hash>.pandas.json`.


@ditto.pandas.json
def test_fn_with_json_dataframe_snapshot(snapshot):
    input_data = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 9]})
    result = awesome_fn_to_test(input_data)
    pd.testing.assert_frame_equal(result, snapshot(result, key="ab_dataframe"))
```

## Series and index frequency

The same three marks record a `pd.Series`. A Series is stored as a one-column
DataFrame plus a small `ditto` marker that records it was a Series and its
name.

pandas doesn't store a `DatetimeIndex` or `TimedeltaIndex` `freq` in parquet or
JSON, so parquet and JSON snapshots put it in the same marker as
`"index_freq"` and restore it on load. `pd.testing.assert_frame_equal` then
passes without `check_freq=False`, and still catches a change of frequency.
Loading a snapshot whose stored `freq` doesn't fit its dates raises
`ValueError`. CSV doesn't read dates back as a `DatetimeIndex`, so it doesn't
store a `freq`.

A `freq` is only stored if its string rebuilds the same offset. Fixed and
calendar frequencies such as `D`, `2h`, `W-SUN`, `B`, `ME` and `QE-DEC` do. A
`CustomBusinessDay` with its own weekmask or holidays, or a `pd.DateOffset`
built from keywords, doesn't: its index loads back with no `freq`, as pandas
would load it, so compare with `check_freq=False`.

The `freq` is stored as its pandas alias, such as `ME`. pandas has renamed
aliases before (`M` became `ME` in 2.2, `H` became `h`), so a later rename could
make an old snapshot warn or fail to load; record it again if that happens.

| Format | Where the marker lives |
|--------|------------------------|
| parquet | Arrow schema metadata under the key `ditto` |
| json | a top-level `"ditto"` key beside `schema` and `data` |
| csv | a first line: `# ditto: {…}` (Series only) |

A DataFrame without an index `freq` has no marker, so its file is exactly what
pandas writes. Another tool reading a file with a marker ignores it in parquet,
but needs to know about it in JSON and CSV. A Series also reads back as a
one-column frame without it. For CSV, skip the marker with
`pd.read_csv(..., skiprows=1)`.

A marker from a newer version of the plugin fails to load with `ValueError`
rather than loading the wrong thing.

The Series name must be `None`, a `str`, `int`, `float` or `bool`, or a
non-nested tuple of those. A numpy scalar name, as `df.iloc[i]` gives, is
recorded as the matching Python value. Anything else, such as the `Timestamp`
name `df.loc[date]` gives, raises `TypeError` at write time; `rename()` the
Series first.

### Format notes

Only parquet round-trips a DataFrame's or Series' values and dtypes exactly.
JSON and CSV change some values or types on the way through, and a snapshot
comparison then fails even though the code under test didn't change. A Series follows the same index and
dtype rules as a DataFrame in each format.

| Format | Index | Values and dtypes |
|--------|-------|-------------------|
| parquet | preserved, except a non-string name | preserved |
| json | preserved, except as listed below | changed in several cases, listed below |
| csv | single-level only; values re-parsed | re-parsed from text |

**Parquet** keeps every value and dtype, but changes two kinds of name, as
pandas' own `to_parquet` does (it warns that they won't round-trip):

- Column names of mixed types come back as strings: `["a", 0, 1.5]` is read back
  as `["a", "0", "1.5"]`. Column names that are all `int`, all `float` or all
  `bool` keep their type.
- An index name that isn't a string comes back as one: an index named `0` is
  read back named `"0"`.

`pd.testing.assert_frame_equal` then fails on the first run with
`DataFrame.columns are different` or `DataFrame.index are different`. Rename the
columns or the index to strings before recording. A Series name isn't affected.
See [#228](https://github.com/owlowlyowl/pytest-ditto/issues/228).

**JSON** (`to_json(orient="table")`) suits simple frames: `int64`, `bool`,
strings, categoricals, and floats where approximate values are fine. It changes
other data, in the columns and the index alike:

> **Warning: JSON rounds floats without failing the test.** pandas writes floats
> to 10 decimal places, so most floats lose precision, small ones most of all
> (`1.234567e-8` comes back as `1.23e-8`), and values between about `1e-15` and
> `1e-10`, such as `1.23e-12`, are written as `0.0`.
> `pd.testing.assert_frame_equal` passes anyway, since the difference is inside
> its default tolerance, so the snapshot doesn't hold the exact values and a
> later change that small isn't caught. Use `@ditto.pandas.parquet` when exact
> float values matter.

These other changes make the comparison fail, usually on the first run:

- **Datetimes come back in nanoseconds.** pandas 3 creates datetimes in
  microseconds by default, so on pandas 3 **any datetime column or index**
  changes dtype. Convert it first with `.as_unit("ns")`, or use parquet.
- Datetimes are written to the millisecond, so anything finer is truncated.
- `inf` and `-inf` are written as `null` and come back as `NaN`.
- Numeric columns are widened to 64 bits, so `int8`, `int32` and `uint16` come
  back as `int64`, and `float32` as `float64`.
- An index named `index` is read back unnamed, and pandas warns that the name is
  not round-trippable.
- Timedelta, interval and complex data can't be read back, and a period column
  can't be written. A `PeriodIndex` is fine.

**CSV** keeps no type information, so every column and the index are parsed
from text on load:

- Strings that look like numbers become numbers: `"001"` is read back as `1`.
- Strings pandas treats as missing, such as `"NA"`, `"null"` and `""`, become
  `NaN`.
- dtypes are inferred again, so `int32` comes back as `int64`, and categoricals
  come back as plain strings.
- Only a single-level index is supported. `DatetimeIndex`, `PeriodIndex`,
  `CategoricalIndex` and `MultiIndex` are not. Recording a Series with a
  `MultiIndex` raises `ValueError`.
- A `RangeIndex` may come back as a plain integer index, depending on the pandas
  version. Pass `check_index_type=False` to `pd.testing.assert_frame_equal` to
  allow for that. It does not help with any of the changed values above.

Use `@ditto.pandas.parquet` for DataFrames or Series that hit any of these
cases.
