from pathlib import Path
from typing import ClassVar, Any

import pickle


class PickleIO:
    extension: ClassVar[str] = "pkl"

    def save(self, data: Any, filepath: Path) -> None:
        with open(filepath, "wb") as f:
            pickle.dump(data, f)

    def load(self, filepath: Path) -> Any:
        with open(filepath, "rb") as f:
            return pickle.load(f)