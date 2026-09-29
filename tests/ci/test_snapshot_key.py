"""Behavioural tests for SnapshotKey identity and key-format contracts."""

import pytest

from ditto.snapshot import SnapshotKey, _flat_key, _remote_key


def test_filename_uses_short_form() -> None:
    """filename returns the legacy short form 'group@key.ext' without module."""
    sk = SnapshotKey(
        module="tests/bar/test_api", group_name="test_result", key="v", identifier="pkl"
    )

    assert sk.filename == "test_result@v.pkl"


def test_filename_preserves_multi_dot_identifier() -> None:
    """filename preserves a dotted persisted recorder identifier unchanged."""
    sk = SnapshotKey(
        module="tests/bar/test_api",
        group_name="test_result",
        key="v",
        identifier="pandas.parquet",
    )

    assert sk.filename == "test_result@v.pandas.parquet"


def test_str_uses_namespaced_form() -> None:
    """str includes the module so remote backends can distinguish same-named tests
    across files."""
    sk = SnapshotKey(
        module="tests/bar/test_api", group_name="test_result", key="v", identifier="pkl"
    )

    assert str(sk) == "tests/bar/test_api/test_result@v.pkl"


def test_keys_with_different_modules_are_unequal() -> None:
    """Two SnapshotKeys identical except for module are distinct — no cross-file
    collision."""
    a = SnapshotKey(
        module="tests/foo/test_api", group_name="test_result", key="v", identifier="pkl"
    )
    b = SnapshotKey(
        module="tests/bar/test_api", group_name="test_result", key="v", identifier="pkl"
    )

    assert a != b


def test_keys_with_same_fields_are_equal() -> None:
    """Two SnapshotKeys with all equal fields are the same key."""
    a = SnapshotKey(module="m", group_name="g", key="k", identifier="pkl")
    b = SnapshotKey(module="m", group_name="g", key="k", identifier="pkl")

    assert a == b


def test_keys_are_hashable() -> None:
    """SnapshotKey can be stored in a set — required for used_keys tracking."""
    a = SnapshotKey(module="m", group_name="g", key="k", identifier="pkl")
    b = SnapshotKey(module="m", group_name="g", key="k", identifier="pkl")

    assert {a, b} == {a}


def test_flat_key_uses_dotted_module_prefix() -> None:
    """_flat_key replaces slashes in module with dots for flat filesystem storage."""
    sk = SnapshotKey(
        module="tests/bar/test_api", group_name="test_result", key="v", identifier="pkl"
    )

    assert _flat_key(sk) == "tests.bar.test_api.test_result@v~c5e27e24f97330cd.pkl"


def test_flat_key_with_class_prefix() -> None:
    """_flat_key includes the class prefix in group_name unchanged."""
    sk = SnapshotKey(
        module="tests/bar/test_api",
        group_name="TestClass.test_result",
        key="v",
        identifier="pkl",
    )

    expected = "tests.bar.test_api.TestClass.test_result@v~927068995fd03a0b.pkl"
    assert _flat_key(sk) == expected


def test_flat_key_preserves_multi_dot_extension() -> None:
    """_flat_key preserves multi-part extensions like 'pandas.parquet'."""
    sk = SnapshotKey(
        module="tests/bar/test_api",
        group_name="test_result",
        key="v",
        identifier="pandas.parquet",
    )

    expected = "tests.bar.test_api.test_result@v~4956086b5a19330d.pandas.parquet"
    assert _flat_key(sk) == expected


def test_display_name_always_uses_namespaced_form() -> None:
    """display_name always returns 'module/group@key.ext'."""
    sk = SnapshotKey(
        module="tests/bar/test_api", group_name="test_result", key="v", identifier="pkl"
    )

    assert sk.display_name == "tests/bar/test_api/test_result@v.pkl"


def test_different_keys_within_same_group_are_unequal() -> None:
    """Different key values within the same test group produce distinct SnapshotKeys."""
    a = SnapshotKey(module="m", group_name="g", key="first", identifier="pkl")
    b = SnapshotKey(module="m", group_name="g", key="second", identifier="pkl")

    assert a != b


# Stored names are part of the on-disk format: these pin the label rules and the
# identity hash (the first 16 hex characters of the SHA-256 of the compact JSON
# array `[test, key, identifier]`, UTF-8 encoded, where `test` is the node id or,
# for these keys without one, `module::group_name`). A change that alters any of
# them renames every stored snapshot.
@pytest.mark.parametrize(
    ("sk", "expected"),
    [
        (
            SnapshotKey("tests/test_api", "test_get[12:00]", "body", "json"),
            "tests.test_api.test_get[12_00]@body~65d95e2289583fbe.json",
        ),
        # Parametrize IDs that differ only in case get different hashes, so the
        # names stay distinct on case-insensitive file systems.
        (
            SnapshotKey("tests/test_api", "test_get[A]", "body", "json"),
            "tests.test_api.test_get[A]@body~e75a3e9463ed27a3.json",
        ),
        (
            SnapshotKey("tests/test_api", "test_get[a]", "body", "json"),
            "tests.test_api.test_get[a]@body~6c1f73a9ca679015.json",
        ),
        # Non-ASCII is hashed as UTF-8 and replaced in the label.
        (SnapshotKey("m", "g", "é", "json"), "m.g@_~6ae7a9a90b0bf66f.json"),
        # `@`, `/` and `~` in a key are replaced, so the label stays parsable.
        (SnapshotKey("m", "g", "a@b/c~d", "json"), "m.g@a_b_c_d~3f0cb79ff7d7bdc9.json"),
        # The group name keeps 80 characters and the key 40.
        (
            SnapshotKey("m", "t[" + "x" * 100 + "]", "k" * 50, "json"),
            "m.t[" + "x" * 78 + "@" + "k" * 40 + "~280df326dbc13db2.json",
        ),
    ],
    ids=["replaced-char", "upper", "lower", "non-ascii", "separators", "shortened"],
)
def test_flat_key_labels_and_hashes_the_identity(sk, expected) -> None:
    """A file name is the module, a readable label and a hash of the identity."""
    assert _flat_key(sk) == expected


def test_remote_key_uses_slash_after_the_module() -> None:
    """Remote keys are the file name's label and hash, after `module/`."""
    sk = SnapshotKey("tests/test_api", "test_get[12:00]", "body", "json")

    expected = "tests/test_api/test_get[12_00]@body~65d95e2289583fbe.json"
    assert _remote_key(sk) == expected


def test_str_is_the_readable_identity_not_a_storage_key() -> None:
    """`str()` keeps every character and has no hash; reports show it."""
    sk = SnapshotKey("tests/test_api", "test_get[12:00]", "body", "json")

    assert str(sk) == "tests/test_api/test_get[12:00]@body.json"
