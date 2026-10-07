# pytest-ditto-polars

A [pytest-ditto](https://github.com/owlowlyowl/pytest-ditto) plugin for polars DataFrame snapshots.

**[Documentation](https://owlowlyowl.github.io/pytest-ditto/plugins/polars/)**

## Installation

```bash
pip install "pytest-ditto[polars]"
```

## Marks

- `@ditto.polars.parquet`
- `@ditto.polars.ipc`
- `@ditto.polars.csv`
- `@ditto.polars.ndjson`

Each mark is shorthand for `@ditto.record("<name>")`.

**Use `@ditto.polars.parquet`**: it round-trips every dtype, and unlike IPC its
format is stable across polars versions. See the format notes in the
documentation.

## Usage

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
