from pathlib import Path
from typing import ClassVar

import pandas as pd

from ditto.io._protocol import Base


class PandasParquet(Base):
    extension: ClassVar[str] = "parquet"

    @staticmethod
    def save(data: pd.DataFrame, filepath: Path) -> None:
        data.to_parquet(filepath)

    @staticmethod
    def load(filepath: Path) -> pd.DataFrame:
        return pd.read_parquet(filepath)
