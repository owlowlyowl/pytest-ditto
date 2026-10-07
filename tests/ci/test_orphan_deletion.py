from pathlib import Path

import pytest

from ditto.exceptions import DittoWarning
from ditto.plugin._drift import (
    FailedDeletion,
    Orphan,
    PruneResult,
    delete_orphans,
    local_target_ids,
    split_shared,
)
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


def test_returns_the_orphans_deleted() -> None:
    """The result lists the deleted orphans, in orphan order, and no failures."""
    backend = {"a@k.json": b"1", "b@k.json": b"2"}
    orphans = [Orphan("t", backend, "a@k.json"), Orphan("t", backend, "b@k.json")]

    actual = delete_orphans(orphans)

    expected = PruneResult(deleted=orphans, failed=[])
    assert actual == expected


def test_records_a_failed_deletion_with_its_reason_and_deletes_the_rest() -> None:
    """A deletion that raises is recorded with the error, and the remaining
    orphans are still deleted."""
    stuck = Orphan("t", _UndeletableBackend({"stuck@k.json": b"1"}), "stuck@k.json")
    gone = Orphan("t", {"gone@k.json": b"2"}, "gone@k.json")

    actual = delete_orphans([stuck, gone])

    expected = PruneResult(
        deleted=[gone], failed=[FailedDeletion(stuck, "read-only store")]
    )
    assert actual == expected


def _file_target(path) -> _RegisteredTarget:
    return _RegisteredTarget(f"file://{path.as_posix()}", "file", {})


def test_treats_orphans_as_shared_when_their_target_is_not_local() -> None:
    """Only orphans whose target id is in the local ids count as local."""
    local = Orphan(".ditto", {}, "a")
    shared = Orphan("s3://bucket/snaps", {}, "b")

    actual = split_shared([local, shared], local_ids={".ditto"})

    expected = ([local], [shared])
    assert actual == expected


def test_local_target_ids_include_only_targets_inside_the_rootdir(tmp_path) -> None:
    """A file target inside the rootdir is local; one outside it or on another
    scheme isn't."""
    root = tmp_path / "project"
    targets = {
        ".ditto": _file_target(root / ".ditto"),
        "outside": _file_target(tmp_path / "outside"),
        "s3://bucket/snaps": _RegisteredTarget("s3://bucket/snaps", "s3", {}),
    }

    actual = local_target_ids(targets, root)

    expected = {".ditto"}
    assert actual == expected


def test_treats_a_target_as_shared_when_its_path_cannot_be_resolved(
    tmp_path, monkeypatch
) -> None:
    """A target whose path can't be resolved is warned about and not local."""
    targets = {".ditto": _file_target(tmp_path / ".ditto")}

    def unresolvable(self, strict=False):
        raise OSError("Symlink loop")

    monkeypatch.setattr(Path, "resolve", unresolvable)

    with pytest.warns(DittoWarning, match="could not resolve '.ditto'"):
        actual = local_target_ids(targets, tmp_path)

    assert actual == set()
