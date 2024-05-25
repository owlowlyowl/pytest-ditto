from pathlib import Path
from typing import ClassVar

import polars as pl

from ditto.io._protocol import Base


class PolarsParquet(Base):
    extension: ClassVar[str] = "polars.parquet"

    @staticmethod
    def save(data: pl.DataFrame, filepath: Path) -> None:
        print("HASDKHKASDHKAJDHKASDHKAJSBQMBQIURQH")
        data.write_parquet(filepath)

    @staticmethod
    def load(filepath: Path) -> pl.DataFrame:
        return pl.read_parquet(filepath)