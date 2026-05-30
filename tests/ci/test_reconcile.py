import fsspec

from ditto._reconcile import ReconcileResult, owned_prefixes, diff_backend
from ditto._lockfile import LockEntry, storage_key
from ditto.snapshot import Snapshot, resolve_snapshot, session_tracker
from ditto.backends import FsspecMapping
from ditto.recorders import default as _default_recorder


def test_owned_prefixes_are_dotted_for_file_scheme():
    """File backends own flat dotted prefixes."""
    actual = owned_prefixes({"tests/test_api"}, "file")

    expected = frozenset({"tests.test_api."})
    assert actual == expected


def test_owned_prefixes_are_slash_separated_for_remote_scheme():
    """Remote backends own slash-separated prefixes."""
    actual = owned_prefixes({"tests/test_api"}, "s3")

    expected = frozenset({"tests/test_api/"})
    assert actual == expected


def test_reports_missing_when_lock_key_absent_from_backend():
    """A key in the lock but not the backend is missing."""
    result = diff_backend(
        lock_keys={"tests.m.test_a@k.pkl"},
        backend_keys=set(),
        owned=frozenset({"tests.m."}),
    )

    assert result.missing == ("tests.m.test_a@k.pkl",)
    assert result.orphan == ()


def test_reports_orphan_when_backend_key_under_owned_prefix_absent_from_lock():
    """A backend key under an owned prefix with no lock entry is an orphan."""
    result = diff_backend(
        lock_keys=set(),
        backend_keys={"tests.m.test_a@k.pkl"},
        owned=frozenset({"tests.m."}),
    )

    assert result.orphan == ("tests.m.test_a@k.pkl",)
    assert result.missing == ()


def test_ignores_backend_keys_outside_owned_prefixes():
    """Keys from another suite/branch on a shared backend are never orphans."""
    result = diff_backend(
        lock_keys=set(),
        backend_keys={"other.suite.test_z@k.pkl"},
        owned=frozenset({"tests.m."}),
    )

    assert result.orphan == ()
    assert result.missing == ()


def test_reports_nothing_when_backend_matches_lock():
    """No drift when the backend's owned keys equal the lock's keys."""
    keys = {"tests.m.test_a@k.pkl"}
    result = diff_backend(
        lock_keys=keys, backend_keys=keys, owned=frozenset({"tests.m."})
    )

    assert result == ReconcileResult(missing=(), orphan=())


def test_classifies_orphans_across_multiple_owned_prefixes():
    """Orphan detection honours every owned prefix, not just the first."""
    result = diff_backend(
        lock_keys=set(),
        backend_keys={
            "tests.a.test_x@k.pkl",
            "tests.b.test_y@k.pkl",
            "other.z@k.pkl",
        },
        owned=frozenset({"tests.a.", "tests.b."}),
    )

    assert result.orphan == ("tests.a.test_x@k.pkl", "tests.b.test_y@k.pkl")


def test_key_in_both_lock_and_backend_is_not_an_orphan():
    """A key present in both the lock and the backend is never an orphan."""
    keys = {"tests.m.test_a@k.pkl"}
    result = diff_backend(
        lock_keys=keys,
        backend_keys=keys | {"tests.m.test_b@k.pkl"},
        owned=frozenset({"tests.m."}),
    )

    assert result.orphan == ("tests.m.test_b@k.pkl",)
    assert result.missing == ()


def test_storage_key_matches_the_key_the_fixture_actually_stores(tmp_path):
    """storage_key(nodeid) equals the backend key a real resolve_snapshot writes."""
    session_tracker.reset()
    root = (tmp_path / ".ditto").as_posix()
    backend = FsspecMapping(fsspec.filesystem("file"), root)
    snap = Snapshot(
        group_name="TestX.test_foo",
        module="tests/test_api",
        target=f"file://{tmp_path}/.ditto",
        _backend=backend,
        recorder=_default_recorder(),
        nodeid="tests/test_api.py::TestX::test_foo",
        target_id="tests/.ditto",
    )
    resolve_snapshot(snap, 123, "k")  # writes the snapshot to the backend

    stored_keys = set(backend)  # the actual storage keys on the backend
    derived = storage_key(
        LockEntry("tests/test_api.py::TestX::test_foo", "k", "pkl"), "file"
    )

    assert derived in stored_keys
    session_tracker.reset()
