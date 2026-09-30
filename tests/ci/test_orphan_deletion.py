import pytest

from ditto.exceptions import DittoWarning
from ditto.plugin._drift import Orphan, delete_orphans, split_shared
from ditto.snapshot import _RegisteredTarget


class _UndeletableBackend(dict[str, bytes]):
    """A backend whose keys cannot be deleted."""

    def __delitem__(self, key: str) -> None:
        raise PermissionError("read-only store")


def test_deletes_every_orphan_from_its_backend() -> None:
    """Each orphan's key is removed from the backend it belongs to."""
    first = {"a@k.json": b"1", "kept@k.json": b"2"}
    second = {"b@k.json": b"3"}

    delete_orphans([Orphan("t", first, "a@k.json"), Orphan("t", second, "b@k.json")])

    assert first == {"kept@k.json": b"2"}
    assert second == {}


def test_returns_the_keys_deleted() -> None:
    """The result lists the deleted keys, in orphan order."""
    backend = {"a@k.json": b"1", "b@k.json": b"2"}
    orphans = [Orphan("t", backend, "a@k.json"), Orphan("t", backend, "b@k.json")]

    actual = delete_orphans(orphans)

    expected = ["a@k.json", "b@k.json"]
    assert actual == expected


def test_omits_and_warns_about_a_key_that_fails_to_delete() -> None:
    """A failed deletion is warned about, left out of the result, and not fatal."""
    stuck = _UndeletableBackend({"stuck@k.json": b"1"})
    backend = {"gone@k.json": b"2"}
    orphans = [Orphan("t", stuck, "stuck@k.json"), Orphan("t", backend, "gone@k.json")]

    with pytest.warns(DittoWarning, match="stuck@k.json.*read-only store"):
        actual = delete_orphans(orphans)

    expected = ["gone@k.json"]
    assert actual == expected


def _target(uri: str) -> _RegisteredTarget:
    return _RegisteredTarget(uri, uri.partition(":")[0], {})


def test_split_shared_classifies_each_target_from_its_uri(tmp_path) -> None:
    """Orphans in a target inside the rootdir are local; the rest, including
    a target that was never registered, are shared."""
    targets = {
        ".ditto": _target(f"file://{(tmp_path / '.ditto').as_posix()}"),
        "s3://bucket/snaps": _target("s3://bucket/snaps"),
    }
    local = Orphan(".ditto", {}, "a")
    remote = Orphan("s3://bucket/snaps", {}, "b")
    unknown = Orphan("elsewhere", {}, "c")

    assert split_shared([local, remote, unknown], targets, tmp_path) == (
        [local],
        [remote, unknown],
    )


def test_split_shared_treats_an_unresolvable_target_as_shared(
    tmp_path, monkeypatch
) -> None:
    """A target whose path can't be resolved is warned about and not pruned."""
    uri = f"file://{(tmp_path / '.ditto').as_posix()}"

    def unresolvable(canonical_uri, rootdir):
        raise OSError("Symlink loop")

    monkeypatch.setattr("ditto.plugin._drift.is_checkout_local", unresolvable)
    orphan = Orphan(".ditto", {}, "a")

    with pytest.warns(DittoWarning, match="could not resolve '.ditto'"):
        assert split_shared([orphan], {".ditto": _target(uri)}, tmp_path) == (
            [],
            [orphan],
        )
