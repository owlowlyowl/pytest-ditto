from dataclasses import dataclass

import pytest


@dataclass(frozen=True)
class PolarsMarks:
    parquet: pytest.MarkDecorator


def marks() -> PolarsMarks:
    return PolarsMarks(
        parquet=pytest.mark.record("pandas_parquet"),
    )
