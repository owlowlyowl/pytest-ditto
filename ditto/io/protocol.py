from pathlib import Path
from typing import ClassVar, Any, Protocol


# TODO: maybe use abstract base class instead
class SnapshotIO(Protocol):
    extension: ClassVar[str]

    @staticmethod
    def save(data: Any, filepath: Path) -> None: ...

    @staticmethod
    def load(filepath: Path) -> Any: ...
