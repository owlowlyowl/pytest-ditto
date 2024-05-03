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
        io: io.SnapshotIO = io.PickleIO,
        suffix: str | None = None,
    ) -> None:
        self.path = path
        self.name = name
        self.record = record
        self.io = io
        self.suffix = suffix
        self.data = None

    def filepath(self, suffix: str | None = None) -> Path:
        suffix = suffix if suffix is not None else ""
        identifier = f"{self.name}@{suffix}" if suffix else self.name
        return self.path / f"{identifier}.{self.io.extension}"

    def _save(self, data: Any, suffix: str | None = None) -> None:
        suffix = suffix if suffix is not None else ""
        self.io.save(data, self.filepath(suffix))

    def _load(self, suffix: str | None = None) -> Any:
        suffix = suffix if suffix is not None else ""
        return self.io.load(self.filepath(suffix))

    def __call__(self, data: Any, suffix: str | None = None) -> Any:
        if self.record:
            self._save(data, suffix)
            self.data = data
        else:
            self.data = self._load(suffix)

        return self.data

    def __repr__(self) -> str:
        return self.data.__repr__()

    def __str__(self) -> str:
        return self.data.__str__()
