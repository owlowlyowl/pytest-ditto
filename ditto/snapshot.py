from pathlib import Path
from typing import Any

from ditto import io


class Snapshot:

    data: Any | None

    def __init__(
        self,
        path: Path,
        name: str,
        record: bool = False,
        io: io.Base = io.Pickle,
        identifier: str | None = None,
    ) -> None:
        self.path = path
        self.name = name
        self.record = record
        self.io = io if io is not None else io.default()
        self.identifier = identifier
        self.data = None

    def filepath(self, identifier: str | None = None) -> Path:
        identifier = identifier if identifier is not None else ""
        identifier = f"{self.name}@{identifier}" if identifier else self.name
        return self.path / f"{identifier}.{self.io.extension}"

    def _save(self, data: Any, identifier: str | None = None) -> None:
        identifier = identifier if identifier is not None else ""
        self.io.save(data, self.filepath(identifier))

    def _load(self, identifier: str | None = None) -> Any:
        identifier = identifier if identifier is not None else ""
        return self.io.load(self.filepath(identifier))

    def __call__(self, data: Any, identifier: str | None = None) -> Any:
        # If the snapshot data exists, and we are not recording, load the data from the
        # snapshot file; otherwise, save the data to the snapshot file.

        if self.filepath(identifier).exists():
            self.data = self._load(identifier)

        else:
            self._save(data, identifier)
            self.data = data

        return self.data

    def __repr__(self) -> str:
        return f"{self.__class__.__name__.lower()}({self.data.__repr__()})"

    def __str__(self) -> str:
        return f"{self.__class__.__name__.lower()}({self.data.__str__()})"
