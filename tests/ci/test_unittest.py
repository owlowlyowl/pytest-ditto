import pickle
from pathlib import Path
from urllib.parse import urlparse

import ditto


def _ditto_dir(snapshot: ditto.Snapshot) -> Path:
    """Derive the .ditto directory path from a file:// Snapshot target URI."""
    return Path(urlparse(snapshot.target).path)


class TestDittoTestCaseSnapshot(ditto.DittoTestCase):
    def test_returns_same_instance_on_repeated_access(self):
        """cached_property returns the same Snapshot object across multiple accesses."""
        first = self.snapshot
        second = self.snapshot

        assert first is second

    def test_target_is_adjacent_to_test_file(self):
        """Snapshot files are stored in a .ditto dir next to the test file."""
        expected = (Path(__file__).parent / ".ditto").resolve()

        actual = Path(urlparse(self.snapshot.target).path)

        assert actual == expected

    def test_group_name_is_derived_from_test_id(self):
        """group_name is the last three dot-separated parts of the unittest test ID."""
        expected = ".".join(self.id().split(".")[-3:])

        assert self.snapshot.group_name == expected

    def test_returns_value_on_first_call(self):
        """On first call, snapshot returns the value that was passed to it."""
        snapshot_file = _ditto_dir(self.snapshot) / f"{self.snapshot.group_name}@v.pkl"
        self.addCleanup(snapshot_file.unlink, missing_ok=True)

        actual = self.snapshot({"a": 1}, key="v")

        assert actual == {"a": 1}

    def test_creates_snapshot_file_on_first_call(self):
        """On first call, snapshot writes the value to disk."""
        snapshot_file = _ditto_dir(self.snapshot) / f"{self.snapshot.group_name}@w.pkl"
        self.addCleanup(snapshot_file.unlink, missing_ok=True)

        self.snapshot({"a": 1}, key="w")

        assert snapshot_file.exists()

    def test_loads_stored_value_when_snapshot_file_already_exists(self):
        """snapshot returns the stored value when the snapshot file already exists."""
        ditto_dir = _ditto_dir(self.snapshot)
        snapshot_file = ditto_dir / f"{self.snapshot.group_name}@v2.pkl"
        ditto_dir.mkdir(parents=True, exist_ok=True)
        snapshot_file.write_bytes(pickle.dumps({"b": 2}))
        self.addCleanup(snapshot_file.unlink, missing_ok=True)

        actual = self.snapshot({"b": 99}, key="v2")

        assert actual == {"b": 2}


class TestAwesome(ditto.DittoTestCase):
    def test_roundtrips_dict_produced_by_pure_function(self):
        """Snapshot round-trips a dict value produced by a pure function."""

        def fn(x: dict[str, int]) -> dict[str, int]:
            return {k: v + 1 for k, v in x.items()}

        result = fn({"unittest": 0})
        actual = self.snapshot(result, key="wowow")

        assert actual == result
