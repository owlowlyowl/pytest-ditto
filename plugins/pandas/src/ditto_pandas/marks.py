from dataclasses import dataclass

import pytest


@dataclass(frozen=True)
class PandasMarks:
    parquet: pytest.MarkDecorator
    json: pytest.MarkDecorator
    csv: pytest.MarkDecorator


def marks() -> PandasMarks:
    return PandasMarks(
        parquet=pytest.mark.record("pandas_parquet"),
        json=pytest.mark.record("pandas_json"),
        csv=pytest.mark.record("pandas_csv"),
    )
