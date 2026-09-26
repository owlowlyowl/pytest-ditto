# pytest-ditto-pyarrow

Extension plugin for [`pytest-ditto`](https://github.com/owlowlyowl/pytest-ditto) for `pyarrow` table snapshots.

Use the following marks for their associated recorder:
- `@ditto.pyarrow.parquet`
- `@ditto.pyarrow.feather`
- `@ditto.pyarrow.csv`

## Installation
```bash
pip install pytest-ditto[pyarrow]
```

## Usage
The following test example tests the result of `fn` hasn't changed by comparing against a saved snapshot of the result. This snapshot is taken the first time the test is run; hence, the initial run is not a proper test run. Subsequent test runs are compared against the saved result.

- The fixture, `table` is a `pyarrow.Table` and is the argument to the function under test, `fn`.
- `fn` transforms the data and the test asserts the result of this function in unchanged compared to the initial, hopefully validated, result.
- The output format of the snapshot is parquet as defined by the `@ditto.pyarrow.parquet` mark.

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
    even_filter = pc.bit_wise_and(pc.field("a"), pc.scalar(1)) == pc.scalar(0)
    return x.filter(even_filter)


@ditto.pyarrow.parquet
def test_fn_with_pyarrow_parquet_snapshot(snapshot, table):
    result = fn(table)
    assert result.equals(snapshot(result, key="filtered"))
```
