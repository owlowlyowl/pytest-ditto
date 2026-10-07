"""Where pandas parquet stops keeping every value, as the documentation states."""

import numpy as np
import pandas as pd
import pyarrow as pa
import pytest

from ditto import recorders


@pytest.mark.parametrize(
    "column",
    [[1 + 2j], [1, "a"]],
    ids=["complex", "mixed-object"],
)
def test_parquet_cannot_write_a_column_arrow_cannot_represent(column: list) -> None:
    """Parquet raises rather than writing a column with no Arrow type."""
    frame = pd.DataFrame({"c": column})

    with pytest.raises(pa.ArrowException):
        recorders.get("pandas.parquet").dumps(frame)


def test_parquet_reads_tuple_cells_back_as_arrays() -> None:
    """Parquet loads a cell holding a tuple back as a NumPy array."""
    recorder = recorders.get("pandas.parquet")
    frame = pd.DataFrame({"t": [(1, 2)]})

    actual = recorder.loads(recorder.dumps(frame))["t"].iloc[0]

    assert isinstance(actual, np.ndarray)
