from pathlib import Path
from typing import ClassVar, Any

import json


class JsonIO:
    extension: ClassVar[str] = "json"

    def save(self, data: Any, filepath: Path) -> None:
        with open(filepath, "w") as f:
            json.dump(data, f)

    def load(self, filepath: Path) -> Any:
        with open(filepath, "r") as f:
            return json.load(f)