from pathlib import Path
from typing import ClassVar, Any, Protocol


class Base(Protocol):
    extension: ClassVar[str]

    @staticmethod
    def save(data: Any, filepath: Path) -> None: ...

    @staticmethod
    def load(filepath: Path) -> Any: ...
