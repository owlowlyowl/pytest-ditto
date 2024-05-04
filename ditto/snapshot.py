from pathlib import Path
from typing import Any
import pytest

from ditto import io


class Snapshot:

    data: Any | None

    def __init__(
        self,
        path: Path,
        name: str,
        record: bool = False,
        io: io.SnapshotIO = io.PickleIO,
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

        # TODO: At the moment there is no way to re-record snapshots. The approach is to
        #  manually delete the snapshot files and re-run the tests. Using another mark,
        #  e.g., 'record' might be a good way to do this?
        if self.filepath(identifier).exists():
            self.data = self._load(identifier)

        else:
            self._save(data, identifier)
            self.data = data

            _msg = (
                f"\nNo snapshot found: {identifier=}"
                f"\nRecoding new snapshot to {self.filepath(identifier)!r}. "
                "\nRun again to test with recorded snapshot."
            )

            # FIXME: For tests that contain multiple snapshots, when initially recording
            #  the snapshot files, this call to pytest.skip results in the test exiting
            #  early and the remaining snapshots to remain unsaved. This means we need
            #  to run the test N times to get all snapshot files saved, where N is the
            #  number of snapshot calls in the test.
            pytest.skip(_msg)

        return self.data

    def __repr__(self) -> str:
        return f"{self.__class__.__name__.lower()}({self.data.__repr__()})"

    def __str__(self) -> str:
        return f"{self.__class__.__name__.lower()}({self.data.__str__()})"
