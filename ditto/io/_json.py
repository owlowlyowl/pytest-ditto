from pathlib import Path
from typing import ClassVar, Any

import json


class JsonIO:
    extension: ClassVar[str] = "json"

    @staticmethod
    def save(data: Any, filepath: Path) -> None:
        with open(filepath, "w") as f:
            json.dump(data, f)

    @staticmethod
    def load(filepath: Path) -> Any:
        with open(filepath, "r") as f:
            return json.load(f)
