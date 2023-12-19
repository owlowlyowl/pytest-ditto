from pathlib import Path
from typing import ClassVar, Any

import yaml


class YamlIO:
    extension: ClassVar[str] = "yaml"

    def save(self, data: Any, filepath: Path) -> None:
        with open(filepath, "w") as f:
            yaml.dump(data, f, Dumper=yaml.SafeDumper)

    def load(self, filepath: Path) -> Any:
        with open(filepath, "r") as f:
            return yaml.load(f, Loader=yaml.SafeLoader)