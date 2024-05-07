from pathlib import Path
from typing import Any

from ditto import io


class Snapshot:

    data: Any | None

    def __init__(
        self,
        path: Path,
        group_name: str,
        io: io.Base = io.Pickle,
        key: str | None = None,
    ) -> None:
        self.path = path
        self.group_name = group_name
        self.io = io if io is not None else io.default()
        self.key = key
        self.data = None

    def filepath(self, key: str) -> Path:
        stem = f"{self.group_name}@{key}"
        return self.path / f"{stem}.{self.io.extension}"

    def save(self, data: Any, key: str) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        self.io.save(data, self.filepath(key))

    def load(self, key: str) -> Any:
        return self.io.load(self.filepath(key))

    def __call__(self, data: Any, key: str) -> Any:
        # If the snapshot data exists, and we are not recording, load the data from the
        # snapshot file; otherwise, save the data to the snapshot file.

        if self.filepath(key).exists():
            self.data = self.load(key)

        else:
            self.save(data, key)
            self.data = data

        return self.data

    def __repr__(self) -> str:
        return f"{self.__class__.__name__.lower()}({self.data.__repr__()})"

    def __str__(self) -> str:
        return f"{self.__class__.__name__.lower()}({self.data.__str__()})"
