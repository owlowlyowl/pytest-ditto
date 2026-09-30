# pytest-ditto-pandas

Extension plugin for [`pytest-ditto`](https://github.com/owlowlyowl/pytest-ditto) for `pandas` DataFrame and Series snapshots.

Use the following marks for their associated recorder:
- `@ditto.pandas.parquet`
- `@ditto.pandas.json`
- `@ditto.pandas.csv`

Each mark is shorthand for `@ditto.record("pandas.<format>")`.

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
DataFrame plus a small `ditto` marker that records it was a Series, its name,
and the column it was written under.

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

A marker from a newer version of the plugin, or one that's incomplete, fails to
load with `ValueError` rather than loading the wrong thing.

The Series name must be `None`, a `str`, `int`, `float` or `bool`, or a
non-nested tuple of those. Anything else raises `TypeError` at write time.

### Format notes

Only parquet round-trips a DataFrame or Series exactly. JSON refuses data it
can't load back as it was, except that it rounds floats. CSV changes some values
or types on the way through, and a snapshot comparison then fails even though
the code under test didn't change. A Series follows the same index and dtype
rules as a DataFrame in each format.

| Format | Index | Values and dtypes |
|--------|-------|-------------------|
| parquet | preserved | preserved |
| json | preserved, or refused | preserved or refused, except floats are rounded |
| csv | single-level only; values re-parsed | re-parsed from text |

**JSON** (`to_json(orient="table")`) raises `ditto.exceptions.DittoUnsupportedDataError`
before writing a DataFrame or Series that has any of these, naming each column
or index level it can't keep:

- An integer column or index other than `int64`, such as `int8`, `int32` or
  `uint16`, or a `float32` one. JSON reads them back as `int64` and `float64`.
- A datetime column or index in any unit but nanoseconds, with or without a
  timezone. JSON reads it back as nanoseconds. **pandas 3 creates datetimes in
  microseconds by default**, so convert them first with `.as_unit("ns")`.
- A timedelta, interval or complex column or index, or a period column. pandas
  can't read these back from JSON, or write a period column to it. A
  `PeriodIndex` is fine.
- An index or index level named `index`. JSON reads it back unnamed.

Nullable integers (`Int64`, `Int32`, ...), `bool`, strings, categoricals and
nanosecond datetimes, including those finer than a millisecond, load back
exactly.

> **Warning: JSON rounds floats.** pandas writes floats to 10 decimal places,
> so most floats lose precision, small ones most of all (`1.234567e-8` comes
> back as `1.23e-8`), and values between about `1e-15` and `1e-10`, such as
> `1.23e-12`, are written as `0.0`. `pd.testing.assert_frame_equal` passes
> anyway, since the difference is inside its default tolerance, so the
> snapshot doesn't hold the exact values and a later change that small isn't
> caught. `inf` and `-inf` are written as `null` and load back as `NaN`. Use
> `@ditto.pandas.parquet` when exact float values matter.

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

Use `@ditto.pandas.parquet` for DataFrames or Series that JSON refuses or rounds,
or that hit any of the CSV cases.
