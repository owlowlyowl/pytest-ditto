import ditto
from pathlib import Path


class TestDittoTestCaseSnapshot(ditto.DittoTestCase):
    def test_returns_same_instance_on_repeated_access(self):
        """cached_property returns the same Snapshot object across multiple accesses."""
        first = self.snapshot
        second = self.snapshot

        assert first is second

    def test_snapshot_path_is_adjacent_to_test_file(self):
        """Snapshot files are stored in a .ditto dir next to the test file."""
        expected = Path(__file__).parent / ".ditto"

        assert self.snapshot.path == expected

    def test_group_name_is_derived_from_test_id(self):
        """group_name is the last three dot-separated parts of the unittest test ID."""
        expected = ".".join(self.id().split(".")[-3:])

        assert self.snapshot.group_name == expected

    def test_saves_value_and_returns_it_on_first_call(self):
        """On first call, snapshot saves data to disk and returns the original value."""
        snapshot_file = self.snapshot.path / f"{self.snapshot.group_name}@v.pkl"
        self.addCleanup(snapshot_file.unlink, missing_ok=True)

        actual = self.snapshot({"a": 1}, key="v")

        assert actual == {"a": 1}
        assert snapshot_file.exists()

    def test_loads_stored_value_on_second_call(self):
        """On second call with an existing snapshot, the stored value is returned."""
        snapshot_file = self.snapshot.path / f"{self.snapshot.group_name}@v2.pkl"
        self.addCleanup(snapshot_file.unlink, missing_ok=True)

        self.snapshot({"b": 2}, key="v2")
        actual = self.snapshot({"b": 99}, key="v2")

        assert actual == {"b": 2}


class TestAwesome(ditto.DittoTestCase):
    def test_dict(self):
        """Snapshot round-trips a dict value produced by a pure function."""

        def fn(x: dict[str, int]) -> dict[str, int]:
            return {k: v + 1 for k, v in x.items()}

        result = fn({"unittest": 0})

        assert result == self.snapshot(result, key="wowow")
