from pathlib import Path
from typing import Any
from collections import defaultdict

from ditto import io


class DittoException(Exception):
    pass


class DittoSecondLoadError(DittoException):
    def __init__(self, filepath: Path) -> None:
        _msg = (
            "Snapshot has been loaded more than \n"
            "once within the same test. \n"
            f"Filepath is {filepath}. \n"
            "If there are multiple snapshots in use within the same test, use the \n"
            "`identifier` parameter to give them unique names. Otherwise, if the \n"
            "snapshot is intentionally being used with the same underlying data, then\n"
            "assign the snapshot call result to a variable to use throughout the test."
        )
        super().__init__(_msg)


class Snapshot:

    # _key_refs = defaultdict(int)
    _save_refs = defaultdict(int)
    _load_refs = defaultdict(int)
    # _key_refs = {}
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
        # should name this stem
        stem = f"{self.name}@{identifier}" if identifier else self.name
        return self.path / f"{stem}.{self.io.extension}"

    def _save(self, data: Any, identifier: str | None = None) -> None:
        identifier = identifier if identifier is not None else ""
        self.io.save(data, self.filepath(identifier))

    def _load(self, identifier: str | None = None) -> Any:
        identifier = identifier if identifier is not None else ""
        return self.io.load(self.filepath(identifier))

    # def add_key(self, key: str) -> None:
    #     self._key_refs.add(key)
    #
    # def is_existing_reference(self, key: str) -> bool:
    #     return key in self._key_refs

    def __call__(self, data: Any, identifier: str) -> Any:
        # If the snapshot data exists, and we are not recording, load the data from the
        # snapshot file; otherwise, save the data to the snapshot file.

        if self.filepath(identifier).exists():
            self.data = self._load(identifier)
            if self._load_refs[identifier] >= 1:
                raise DittoSecondLoadError(self.filepath(identifier))
            self._load_refs[identifier] += 1

        else:
            self._save(data, identifier)
            self.data = data
            self._save_refs[identifier] += 1

        return self.data

    def __repr__(self) -> str:
        return f"{self.__class__.__name__.lower()}({self.data.__repr__()})"

    def __str__(self) -> str:
        return f"{self.__class__.__name__.lower()}({self.data.__str__()})"
