# PyArrow

`pytest-ditto-pyarrow` records PyArrow Tables.

```bash
pip install "pytest-ditto[pyarrow]"
```

It needs pyarrow 16.1.0 or later.

| Mark | Recorder | Stores |
|------|----------|--------|
| `@ditto.pyarrow.parquet` | `pyarrow.parquet` | Parquet, through `pyarrow.parquet.write_table` |
| `@ditto.pyarrow.feather` | `pyarrow.feather` | Feather (Arrow IPC), through `pyarrow.feather.write_feather` |
| `@ditto.pyarrow.csv` | `pyarrow.csv` | CSV, through `pyarrow.csv.write_csv` |

## Usage

Compare tables with `Table.equals`, which compares the schema as well as the
values:

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

## Format notes

**Parquet** and **Feather** keep a table's types, values and schema metadata,
including timezones, durations, decimals, dictionary, list and struct columns.
Prefer one of them.

**CSV** keeps no types: every column is inferred again from text on load, and
schema metadata is dropped. Among the changes:

- Narrow and specialised types are widened: `int8` comes back as `int64`,
  `float32` as `double`, `decimal128` as `double`, `large_string` as `string`,
  and a dictionary column as plain strings.
- Strings that look like numbers become numbers: `"001"` comes back as `1`.
- A null string comes back as an empty string.
- A duration comes back as a plain integer, and a timestamp in nanoseconds.
- List and struct columns can't be written.
- In a single-column table, a row whose value is null is written as an empty
  line, which isn't read back, so the table loses that row.

Use CSV only for simple tables of ints, floats and non-empty strings that you
want to read as text.
