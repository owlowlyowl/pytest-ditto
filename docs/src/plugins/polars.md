# polars

`pytest-ditto-polars` records polars DataFrames.

```bash
pip install "pytest-ditto[polars]"
```

It needs polars 1.0 or later.

| Mark | Recorder | Stores |
|------|----------|--------|
| `@ditto.polars.parquet` | `polars.parquet` | Parquet, through `DataFrame.write_parquet` |
| `@ditto.polars.ipc` | `polars.ipc` | Arrow IPC, through `DataFrame.write_ipc` |
| `@ditto.polars.csv` | `polars.csv` | CSV, through `DataFrame.write_csv` |
| `@ditto.polars.ndjson` | `polars.ndjson` | Newline-delimited JSON, through `DataFrame.write_ndjson` |

## Usage

Compare frames with `polars.testing.assert_frame_equal`:

```python
import polars as pl
import polars.testing

import ditto


def awesome_fn_to_test(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(pl.col("a") * 2)


# The following test uses polars.DataFrame.write_parquet to write the data snapshot
# to the `.ditto` directory with filename:
# `<module>.test_fn_with_parquet_dataframe_snapshot@ab_dataframe~<hash>.polars.parquet`.


@ditto.polars.parquet
def test_fn_with_parquet_dataframe_snapshot(snapshot):
    input_data = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 9]})
    result = awesome_fn_to_test(input_data)
    pl.testing.assert_frame_equal(result, snapshot(result, key="ab_dataframe"))
```

## Format notes

| Format | Types and values |
|--------|------------------|
| parquet | preserved |
| ipc | preserved |
| csv | re-inferred from text; see below |
| ndjson | re-inferred from JSON; see below |

Prefer `@ditto.polars.parquet` or `@ditto.polars.ipc`, which load back each
column's type and values.

**CSV** and **NDJSON** keep no type information, so each column's type is
inferred again on load:

- Narrow numeric types are widened: `Int8` comes back as `Int64`, and
  `Float32` as `Float64`.
- In CSV, strings that look like numbers become numbers: `"001"` comes back as
  `1`. NDJSON quotes strings, so it keeps them.
- Don't use either for categoricals, enums, nested or temporal columns.
