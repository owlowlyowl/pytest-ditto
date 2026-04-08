from collections.abc import Iterator, MutableMapping
from contextlib import AbstractContextManager
from unittest.mock import Mock

import pytest

from ditto import recorders
from ditto.exceptions import AdditionalMarkError, DittoMarkHasNoIOType
from ditto.plugin import _maybe_enter, _resolve_recorder, _entered_backends

json_recorder = recorders.get("json")
pickle_recorder = recorders.get("pickle")
yaml_recorder = recorders.get("yaml")


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


def test_maybe_enter_returns_entered_object_on_repeated_calls() -> None:
    """_maybe_enter returns the __enter__ result consistently, not the original."""
    _entered_backends.clear()
    backend = _WrappingBackend()

    first = _maybe_enter(backend)
    second = _maybe_enter(backend)

    assert first is backend.wrapper
    assert second is backend.wrapper
    assert first is second
    _entered_backends.clear()
