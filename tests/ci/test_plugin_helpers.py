from unittest.mock import Mock

import pytest

from ditto import recorders
from ditto.exceptions import AdditionalMarkError, DittoMarkHasNoIOType
from ditto.plugin import _resolve_recorder

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
