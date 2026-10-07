# pytest-ditto-pandas

A [pytest-ditto](https://github.com/owlowlyowl/pytest-ditto) plugin for pandas DataFrame and Series snapshots.

**[Documentation](https://owlowlyowl.github.io/pytest-ditto/plugins/pandas/)**

## Installation

```bash
pip install "pytest-ditto[pandas]"
```

It needs pandas 2.2 or later and pyarrow 16.1.0 or later.

## Marks

- `@ditto.pandas.parquet`
- `@ditto.pandas.json`
- `@ditto.pandas.csv`

Each mark is shorthand for `@ditto.record("<name>")`.

**Use `@ditto.pandas.parquet` unless you need a snapshot you can read as text.**
It's the only format that keeps every dtype and value exactly. JSON and CSV
change some data on the way through, including rounding floats without failing
the test; see the format notes in the documentation.

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
