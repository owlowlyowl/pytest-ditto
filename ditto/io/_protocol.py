from pathlib import Path
from typing import ClassVar, Any
from abc import ABCMeta, abstractmethod


class Base(metaclass=ABCMeta):
    extension: ClassVar[str]

    @staticmethod
    @abstractmethod
    def save(data: Any, filepath: Path) -> None: ...

    @staticmethod
    @abstractmethod
    def load(filepath: Path) -> Any: ...
