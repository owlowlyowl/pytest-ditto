from pathlib import Path
from typing import ClassVar, Any

import pickle


class Pickle:
    extension: ClassVar[str] = "pkl"

    @staticmethod
    def save(data: Any, filepath: Path) -> None:
        with open(filepath, "wb") as f:
            pickle.dump(data, f)

    @staticmethod
    def load(filepath: Path) -> Any:
        with open(filepath, "rb") as f:
            return pickle.load(f)
