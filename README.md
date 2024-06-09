# pytest-ditto
[![PyPI version](https://badge.fury.io/py/pytest-ditto.svg)](https://badge.fury.io/py/pytest-ditto)
[![Continuous Integration](https://github.com/owlowlyowl/pytest-ditto/actions/workflows/ci.yml/badge.svg)](https://github.com/owlowlyowl/pytest-ditto/actions/workflows/ci.yml)

Snapshot testing pytest plugin with minimal ceremony and flexible persistence formats.

## Introduction
The `pytest-ditto` plugin is intended to be used snapshot/regression testing. There are
two key components: the `snapshot` fixture and the snapshot persistence formats.

### The `snapshot` Fixture
In the following basic example, the function to test is `fn`, the test is using the
`snapshot` fixture and it is asserting that the result of calling the `fn` with the
value of `x` does not change. 


```python
import ditto


def fn(x: int) -> int:
    return x + 1  # original implementation
    # return x + 2  # new implementation


def test_fn(snapshot) -> None:
    x = 1
    result = fn(x)
    assert result == snapshot(result, key="fn")
```

The first time the test is run, the `snapshot` fixture takes the data passed to it and
persists it to a `.ditto` directory in the same location as the test module. Subsequent
test runs will load the file and use that value in the test to test the output of the
computed value.

By default, the snapshot data is converted and persisted using `pickle`; however, there
are a range of persistence formats that can be used.

### @ditto Marks
If the default persistence format, `pickle`, isn't appropriate different formats can be
specified per test by using `ditto` marks - customised `pytest` mark decorators.

The default persistence types are: `pickle`, `yaml` and `json`; however additional
plugins can be installed as per below:
- `pandas` via `pytest-ditto-pandas`
    - `@ditto.pandas.parquet`
    - `@ditto.pandas.json`
    - `@ditto.pandas.csv`
- `pyarrow` via `pytest-ditto-pyarrow`
    - `@ditto.pyarrow.parquet`
    - `@ditto.pyarrow.feather`
    - `@ditto.pyarrow.csv`


## Usage

### `pd.DataFrame`

Install `pytest-ditto[pandas]` to make `pandas` IO types available.

```python
import pandas as pd

import ditto


def awesome_fn_to_test(df: pd.DataFrame):
    df.loc[:, "a"] *= 2
    return df


@ditto.pandas.parquet
def test_fn_with_parquet_dataframe_snapshot(snapshot):
    input_data = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 9]})
    result = awesome_fn_to_test(input_data)
    pd.testing.assert_frame_equal(result, snapshot(result, key="ab_dataframe"))


@ditto.pandas.json
def test_fn_with_json_dataframe_snapshot(snapshot):
    input_data = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 9]})
    result = awesome_fn_to_test(input_data)
    pd.testing.assert_frame_equal(result, snapshot(result, key="ab_dataframe"))
```

For the above example the snapshot files would be found in the following locations:
- `.ditto/test_fn_with_parquet_dataframe_snapshot@ab_dataframe.pandas.parquet`
- `.ditto/test_fn_with_json_dataframe_snapshot@ab_dataframe.pandas.json`


### `pyarrow.Table`

Install `pytest-ditto[pyarrow]` to make `pyarrow` IO types available.

```python
import pyarrow as pa
import pyarrow.compute as pc
import ditto
import pytest


@pytest.fixture
def table() -> pa.Table:
    return pa.table(
        [
            [1, 2, 3, 4],
            [4.5, 5.2, 6.8, 3.5],
            [7, 8.5, None, None],
            [True, False, True, True],
            ["a", "b", "c", "x"],
        ],
        names=list("abcde"),
    )


def fn(x: pa.Table):
    even_filter = (pc.bit_wise_and(pc.field("a"), pc.scalar(1)) == pc.scalar(0))
    return x.filter(even_filter)


@ditto.pyarrow.parquet
def test_fn_with_pyarrow_parquet_snapshot(snapshot, table):
    result = fn(table)
    assert result.equals(snapshot(result, key="filtered"))
```

For the above example the snapshot files would be found in the following location:
- `.ditto/test_fn_with_pyarrow_parquet_snapshot@filtered.pyarrow.parquet`
