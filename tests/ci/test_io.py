import pandas as pd
import pytest

from ditto import io


@pytest.mark.parametrize(
    ("data", "io_class"),
    [
        pytest.param(data, io.get(io_type), id=io_type)
        for data, io_type in [
            (1, io.IO.PICKLE),
            (2, io.IO.JSON),
            (3, io.IO.YAML),
            (pd.DataFrame({"a": [1, 2], "b": [3, 4]}), io.IO.PANDAS_PARQUET),
        ]
    ],
)
def test_io_save(tmp_dir, data, io_class: io.Base) -> None:
    filepath = tmp_dir / f"tmp.{io_class.extension}"
    io_class.save(data, filepath)
    assert filepath.exists()
