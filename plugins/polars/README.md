# pytest-ditto-polars

Extension plugin for [`pytest-ditto`](https://github.com/owlowlyowl/pytest-ditto) for `polars` DataFrame snapshots.

Use the following marks for their associated recorder:
- `@ditto.polars.parquet`
- `@ditto.polars.ipc`
- `@ditto.polars.csv`
- `@ditto.polars.ndjson`

Each mark is shorthand for `@ditto.record("polars.<format>")`.

## Installation
```bash
pip install pytest-ditto[polars]
```

## Usage

```python
import polars as pl
import polars.testing

import ditto


def awesome_fn_to_test(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(pl.col("a") * 2)


# The following test uses polars.DataFrame.write_parquet to write the data snapshot
# to the `.ditto` directory with filename:
# `<module>.test_fn_with_parquet_dataframe_snapshot@ab_dataframe.polars.parquet`.


@ditto.polars.parquet
def test_fn_with_parquet_dataframe_snapshot(snapshot):
    input_data = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 9]})
    result = awesome_fn_to_test(input_data)
    pl.testing.assert_frame_equal(result, snapshot(result, key="ab_dataframe"))
```

### Format notes

Prefer `@ditto.polars.parquet`. It round-trips a DataFrame's values and dtypes.
The other formats are available when you need them, with these limits:

| Format | Values and dtypes |
|--------|-------------------|
| parquet | preserved |
| ipc | preserved; Polars marks `write_ipc` unstable, so snapshots can break across Polars versions |
| csv | re-inferred from text |
| ndjson | re-inferred from JSON |

**IPC** uses Polars' Arrow IPC writer. Polars documents `write_ipc` as
unstable, so a snapshot recorded on one Polars version may fail to load or
compare on another even if the DataFrame under test did not change.

**CSV** and **NDJSON** keep no type metadata, so dtypes are inferred again on
load. Frames of ints, floats, and strings round-trip in the plugin tests.
Do not use these formats for categoricals, enums, nested, or temporal columns.
