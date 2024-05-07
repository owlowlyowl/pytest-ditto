# pytest-ditto
[![PyPI version](https://badge.fury.io/py/pytest-ditto.svg)](https://badge.fury.io/py/pytest-ditto)
[![Continuous Integration](https://github.com/owlowlyowl/pytest-ditto/actions/workflows/ci.yml/badge.svg)](https://github.com/owlowlyowl/pytest-ditto/actions/workflows/ci.yml)

Snapshot testing pytest plugin with minimal ceremony and flexible persistence formats.


## Usage

### `pd.DataFrame`

```python
import pandas as pd

import ditto


def awesome_fn_to_test(df: pd.DataFrame):
    df["a"] *= 2
    return df


@ditto.record("pandas_parquet")
def test_save_pandas_dataframe(snapshot):
    input_data = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 9]})
    result = awesome_fn_to_test(input_data)
    pd.testing.assert_frame_equal(result, snapshot(result, key="ab_dataframe"))
```
