import pytest

from ditto.exceptions import DittoWarning
from ditto.plugin._drift import Orphan, delete_orphans


class _UndeletableBackend(dict[str, bytes]):
    """A backend whose keys cannot be deleted."""

    def __delitem__(self, key: str) -> None:
        raise PermissionError("read-only store")


def test_deletes_every_orphan_from_its_backend() -> None:
    """Each orphan's key is removed from the backend it belongs to."""
    first = {"a@k.json": b"1", "kept@k.json": b"2"}
    second = {"b@k.json": b"3"}

    delete_orphans([Orphan(first, "a@k.json"), Orphan(second, "b@k.json")])

    assert first == {"kept@k.json": b"2"}
    assert second == {}


def test_returns_the_keys_deleted() -> None:
    """The result lists the deleted keys, in orphan order."""
    backend = {"a@k.json": b"1", "b@k.json": b"2"}
    orphans = [Orphan(backend, "a@k.json"), Orphan(backend, "b@k.json")]

    actual = delete_orphans(orphans)

    expected = ["a@k.json", "b@k.json"]
    assert actual == expected


def test_omits_and_warns_about_a_key_that_fails_to_delete() -> None:
    """A failed deletion is warned about, left out of the result, and not fatal."""
    stuck = _UndeletableBackend({"stuck@k.json": b"1"})
    backend = {"gone@k.json": b"2"}
    orphans = [Orphan(stuck, "stuck@k.json"), Orphan(backend, "gone@k.json")]

    with pytest.warns(DittoWarning, match="stuck@k.json.*read-only store"):
        actual = delete_orphans(orphans)

    expected = ["gone@k.json"]
    assert actual == expected
