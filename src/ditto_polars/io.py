from pathlib import Path
from typing import ClassVar

import polars as pl


class PolarsParquet:
    extension: ClassVar[str] = "polars.parquet"

    @staticmethod
    def save(data: pl.DataFrame, filepath: Path) -> None:
        data.write_parquet(filepath)

    @staticmethod
    def load(filepath: Path) -> pl.DataFrame:
        return pl.read_parquet(filepath)