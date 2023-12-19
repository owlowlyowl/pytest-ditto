from pathlib import Path
from typing import Protocol, ClassVar, Any


class SnapshotIO(Protocol):
    extension: ClassVar[str]

    def save(self, data: Any, filepath: Path) -> None:
        ...

    def load(self, filepath: Path) -> Any:
        ...