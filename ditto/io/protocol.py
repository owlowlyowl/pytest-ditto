from pathlib import Path
from typing import ClassVar, Any

try:
    from typing import Protocol
except ImportError:
    from typing_extensions import Protocol


class SnapshotIO(Protocol):
    extension: ClassVar[str]

    def save(self, data: Any, filepath: Path) -> None:
        ...

    def load(self, filepath: Path) -> Any:
        ...
