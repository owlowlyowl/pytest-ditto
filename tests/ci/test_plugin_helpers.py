from collections.abc import Iterator, MutableMapping
from contextlib import AbstractContextManager
from pathlib import Path
from unittest.mock import Mock

import fsspec.core
import pytest

from ditto.backends import BACKEND_REGISTRY
from ditto import recorders
from ditto.exceptions import AdditionalMarkError, DittoMarkHasNoIOType
from ditto.plugin import (
    _backend_cache,
    _entered_backends,
    _freeze_options,
    _maybe_enter,
    _resolve_recorder,
    _resolve_target,
    _resolve_uri,
)

json_recorder = recorders.get("json")
pickle_recorder = recorders.get("pickle")
yaml_recorder = recorders.get("yaml")


@pytest.fixture(autouse=True)
def _clear_backend_state() -> Iterator[None]:
    _entered_backends.clear()
    _backend_cache.clear()
    yield
    _entered_backends.clear()
    _backend_cache.clear()


def _mark(*args):
    """Construct a minimal fake pytest mark with the given args."""
    m = Mock()
    m.args = args
    return m


# --- _resolve_recorder ---


def test_resolves_to_pickle_when_no_marks_present() -> None:
    """No record marks defaults to the pickle recorder."""
    actual = _resolve_recorder([])

    assert actual is pickle_recorder


def test_resolves_to_pickle_when_pickle_mark_is_present() -> None:
    """A record mark naming 'pickle' resolves to the pickle recorder."""
    actual = _resolve_recorder([_mark("pickle")])

    assert actual is pickle_recorder


def test_resolves_to_yaml_when_yaml_mark_is_present() -> None:
    """A record mark naming 'yaml' resolves to the yaml recorder."""
    actual = _resolve_recorder([_mark("yaml")])

    assert actual is yaml_recorder


def test_resolves_to_json_when_json_mark_is_present() -> None:
    """A record mark naming 'json' resolves to the json recorder."""
    actual = _resolve_recorder([_mark("json")])

    assert actual is json_recorder


def test_raises_when_mark_carries_no_args() -> None:
    """A bare record mark with no arguments raises DittoMarkHasNoIOType."""
    with pytest.raises(DittoMarkHasNoIOType):
        _resolve_recorder([_mark()])


def test_raises_when_mark_names_unregistered_recorder() -> None:
    """An unrecognised recorder name raises DittoMarkHasNoIOType, not a fallback."""
    with pytest.raises(DittoMarkHasNoIOType):
        _resolve_recorder([_mark("nonexistent")])


def test_raises_when_multiple_marks_are_present() -> None:
    """More than one record mark raises AdditionalMarkError."""
    with pytest.raises(AdditionalMarkError):
        _resolve_recorder([_mark("pickle"), _mark("json")])


# --- _maybe_enter ---


class _WrappingBackend(AbstractContextManager, MutableMapping[str, bytes]):
    """A context manager whose __enter__ returns a different wrapper object."""

    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}
        self.wrapper: dict[str, bytes] = {}

    def __enter__(self) -> dict[str, bytes]:
        return self.wrapper

    def __exit__(self, *_: object) -> None:
        pass

    def __getitem__(self, k: str) -> bytes:
        return self._data[k]

    def __setitem__(self, k: str, v: bytes) -> None:
        self._data[k] = v

    def __delitem__(self, k: str) -> None:
        del self._data[k]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)


class _CountingBackend(AbstractContextManager, MutableMapping[str, bytes]):
    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}
        self.enter_calls = 0

    def __getitem__(self, key: str) -> bytes:
        return self._data[key]

    def __setitem__(self, key: str, value: bytes) -> None:
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        del self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __enter__(self) -> "_CountingBackend":
        self.enter_calls += 1
        return self

    def __exit__(self, *_: object) -> None:
        pass


def test_returns_entered_value_on_every_call_when_backend_is_context_manager() -> None:
    """The value returned by __enter__ is returned on every call, not the original backend."""
    _entered_backends.clear()
    backend = _WrappingBackend()

    first = _maybe_enter(backend)
    second = _maybe_enter(backend)

    assert first is backend.wrapper
    assert second is backend.wrapper
    assert first is second


# --- URI resolution ---


def test_freeze_options_handles_nested_mappings_sequences_and_sets() -> None:
    actual = _freeze_options(
        {"items": [1, {"flags": {"a", "b"}}], "token": "abc"}
    )

    assert actual == (
        ("items", (1, (("flags", frozenset({"a", "b"})),))),
        ("token", "abc"),
    )


def test_resolve_uri_caches_relative_file_target_by_canonical_path(tmp_path) -> None:
    first_backend, first_uri = _resolve_uri("file://.ditto", tmp_path, {})
    second_backend, second_uri = _resolve_uri("file://.ditto", tmp_path, {})

    expected = f"file://{(tmp_path / '.ditto').resolve().as_posix()}"
    assert first_uri == expected
    assert second_uri == expected
    assert first_backend is second_backend


def test_resolve_uri_caches_registered_backend_by_uri_and_options(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def factory(uri: str, **opts: str) -> MutableMapping[str, bytes]:
        calls.append((uri, opts))
        return {}

    monkeypatch.setitem(BACKEND_REGISTRY, "demo", factory)

    first_backend, first_uri = _resolve_uri(
        "demo://shared", tmp_path, {"demo": {"token": "abc"}}
    )
    second_backend, second_uri = _resolve_uri(
        "demo://shared", tmp_path, {"demo": {"token": "abc"}}
    )

    assert first_uri == "demo://shared"
    assert second_uri == "demo://shared"
    assert first_backend is second_backend
    assert calls == [("demo://shared", {"token": "abc"})]


def test_resolve_uri_separates_cache_entries_when_options_differ(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def factory(uri: str, **opts: str) -> MutableMapping[str, bytes]:
        calls.append((uri, opts))
        return {}

    monkeypatch.setitem(BACKEND_REGISTRY, "demo", factory)

    first_backend, _ = _resolve_uri("demo://shared", tmp_path, {"demo": {"token": "a"}})
    second_backend, _ = _resolve_uri("demo://shared", tmp_path, {"demo": {"token": "b"}})

    assert first_backend is not second_backend
    assert calls == [
        ("demo://shared", {"token": "a"}),
        ("demo://shared", {"token": "b"}),
    ]


def test_resolve_uri_enters_context_managed_backend_once_per_cache_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    constructed: list[_CountingBackend] = []

    def factory(uri: str, **opts: str) -> MutableMapping[str, bytes]:
        backend = _CountingBackend()
        constructed.append(backend)
        return backend

    monkeypatch.setitem(BACKEND_REGISTRY, "ctx", factory)

    first_backend, _ = _resolve_uri("ctx://shared", tmp_path, {})
    second_backend, _ = _resolve_uri("ctx://shared", tmp_path, {})

    assert len(constructed) == 1
    assert constructed[0].enter_calls == 1
    assert first_backend is second_backend


def test_resolve_uri_raises_for_unknown_scheme(tmp_path) -> None:
    """Unknown schemes raise a ValueError with an install hint."""
    with pytest.raises(ValueError, match="Unknown backend scheme"):
        _resolve_uri("notascheme://target", tmp_path, {})


def test_resolve_uri_forwards_storage_options_to_fsspec(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Scheme-scoped storage options are forwarded to `fsspec.core.url_to_fs`."""
    calls: list[tuple[str, dict[str, str]]] = []
    fake_fs = Mock()

    def fake_url_to_fs(uri: str, **opts: str) -> tuple[Mock, str]:
        calls.append((uri, opts))
        return fake_fs, "/shared-root"

    monkeypatch.setattr(fsspec.core, "url_to_fs", fake_url_to_fs)

    backend, uri = _resolve_uri(
        "memory://shared", tmp_path, {"memory": {"token": "abc"}}
    )

    assert uri == "memory://shared"
    assert getattr(backend, "root") == "/shared-root"
    assert calls == [("memory://shared", {"token": "abc"})]


def test_resolve_target_uses_ini_target_when_no_mark_is_present(tmp_path) -> None:
    """Without a mark, the resolver falls back to `ditto_target`."""
    request = Mock()
    request._fixturemanager.getfixturedefs.return_value = None
    request.node = object()
    request.path = tmp_path / "test_example.py"
    request.getfixturevalue.return_value = {}
    request.config.getini.return_value = "file://.snapshots"

    backend, uri = _resolve_target(None, request)

    assert getattr(backend, "root") == (tmp_path / ".snapshots").resolve().as_posix()
    assert uri == f"file://{(tmp_path / '.snapshots').resolve().as_posix()}"


def test_resolve_target_raises_migration_error_for_user_defined_ditto_backend() -> None:
    """A user-defined `ditto_backend` fixture triggers the migration error."""
    request = Mock()
    request._fixturemanager.getfixturedefs.return_value = [object()]
    request.node = object()

    with pytest.raises(TypeError, match="ditto_backend is superseded"):
        _resolve_target(None, request)
