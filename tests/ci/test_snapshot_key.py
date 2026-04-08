"""Behavioural tests for SnapshotKey identity and key-format contracts."""

from ditto.snapshot import SnapshotKey


def test_filename_uses_short_form() -> None:
    """filename omits the module so on-disk layout matches pre-backend ditto."""
    sk = SnapshotKey(
        module="tests/bar/test_api", group_name="test_result", key="v", extension="pkl"
    )

    assert sk.filename == "test_result@v.pkl"


def test_str_uses_namespaced_form() -> None:
    """str includes the module so remote backends can distinguish same-named tests
    across files."""
    sk = SnapshotKey(
        module="tests/bar/test_api", group_name="test_result", key="v", extension="pkl"
    )

    assert str(sk) == "tests/bar/test_api/test_result@v.pkl"


def test_keys_with_different_modules_are_unequal() -> None:
    """Two SnapshotKeys identical except for module are distinct — no cross-file
    collision."""
    a = SnapshotKey(
        module="tests/foo/test_api", group_name="test_result", key="v", extension="pkl"
    )
    b = SnapshotKey(
        module="tests/bar/test_api", group_name="test_result", key="v", extension="pkl"
    )

    assert a != b


def test_keys_with_same_fields_are_equal() -> None:
    """Two SnapshotKeys with all equal fields are the same key."""
    a = SnapshotKey(module="m", group_name="g", key="k", extension="pkl")
    b = SnapshotKey(module="m", group_name="g", key="k", extension="pkl")

    assert a == b


def test_keys_are_hashable() -> None:
    """SnapshotKey can be stored in a set — required for used_keys tracking."""
    a = SnapshotKey(module="m", group_name="g", key="k", extension="pkl")
    b = SnapshotKey(module="m", group_name="g", key="k", extension="pkl")

    assert {a, b} == {a}


def test_different_keys_within_same_group_are_unequal() -> None:
    """Different key values within the same test group produce distinct SnapshotKeys."""
    a = SnapshotKey(module="m", group_name="g", key="first", extension="pkl")
    b = SnapshotKey(module="m", group_name="g", key="second", extension="pkl")

    assert a != b
