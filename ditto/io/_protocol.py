from pathlib import Path
from typing import ClassVar, Any
from abc import ABCMeta, abstractmethod


# TODO: Bring back the `Protocol` instead of the abstract base class now that external
#  IO classes can be registered via plugins.


class Base(metaclass=ABCMeta):
    extension: ClassVar[str]

    @staticmethod
    @abstractmethod
    def save(data: Any, filepath: Path) -> None: ...

    @staticmethod
    @abstractmethod
    def load(filepath: Path) -> Any: ...
