"""Behavioural tests for SnapshotKey identity and key-format contracts."""

from ditto.snapshot import SnapshotKey, _flat_key


def test_filename_uses_short_form() -> None:
    """filename returns the legacy short form 'group@key.ext' without module."""
    sk = SnapshotKey(
        module="tests/bar/test_api", group_name="test_result", key="v", extension="pkl"
    )

    assert sk.filename == "test_result@v.pkl"


def test_filename_preserves_multi_dot_identifier() -> None:
    """filename preserves a dotted persisted recorder identifier unchanged."""
    sk = SnapshotKey(
        module="tests/bar/test_api",
        group_name="test_result",
        key="v",
        extension="pandas.parquet",
    )

    assert sk.filename == "test_result@v.pandas.parquet"


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


def test_flat_key_uses_dotted_module_prefix() -> None:
    """_flat_key replaces slashes in module with dots for flat filesystem storage."""
    sk = SnapshotKey(
        module="tests/bar/test_api", group_name="test_result", key="v", extension="pkl"
    )

    assert _flat_key(sk) == "tests.bar.test_api.test_result@v.pkl"


def test_flat_key_with_class_prefix() -> None:
    """_flat_key includes the class prefix in group_name unchanged."""
    sk = SnapshotKey(
        module="tests/bar/test_api",
        group_name="TestClass.test_result",
        key="v",
        extension="pkl",
    )

    assert _flat_key(sk) == "tests.bar.test_api.TestClass.test_result@v.pkl"


def test_flat_key_preserves_multi_dot_extension() -> None:
    """_flat_key preserves multi-part extensions like 'pandas.parquet'."""
    sk = SnapshotKey(
        module="tests/bar/test_api",
        group_name="test_result",
        key="v",
        extension="pandas.parquet",
    )

    assert _flat_key(sk) == "tests.bar.test_api.test_result@v.pandas.parquet"


def test_display_name_always_uses_namespaced_form() -> None:
    """display_name always returns 'module/group@key.ext'."""
    sk = SnapshotKey(
        module="tests/bar/test_api", group_name="test_result", key="v", extension="pkl"
    )

    assert sk.display_name == "tests/bar/test_api/test_result@v.pkl"


def test_different_keys_within_same_group_are_unequal() -> None:
    """Different key values within the same test group produce distinct SnapshotKeys."""
    a = SnapshotKey(module="m", group_name="g", key="first", extension="pkl")
    b = SnapshotKey(module="m", group_name="g", key="second", extension="pkl")

    assert a != b
