from dataclasses import dataclass

import pytest


@dataclass(frozen=True)
class PyArrowMarks:
    parquet: pytest.MarkDecorator
    # orc: pytest.MarkDecorator
    feather: pytest.MarkDecorator
    csv: pytest.MarkDecorator


def marks() -> PyArrowMarks:
    return PyArrowMarks(
        parquet=pytest.mark.record("pyarrow_parquet"),
        # orc=pytest.mark.record("pyarrow_orc"),
        feather=pytest.mark.record("pyarrow_feather"),
        csv=pytest.mark.record("pyarrow_csv"),
    )
