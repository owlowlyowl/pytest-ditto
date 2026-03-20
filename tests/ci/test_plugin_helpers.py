from pathlib import Path
from unittest.mock import Mock

import pytest

from ditto.exceptions import AdditionalMarkError, DittoMarkHasNoIOType
from ditto.io._json import Json
from ditto.io._pickle import Pickle
from ditto.io._yaml import Yaml
from ditto.plugin import _resolve_io_type, _snapshot_dir


def _mark(*args):
    """Construct a minimal fake pytest mark with the given args."""
    m = Mock()
    m.args = args
    return m


# --- _resolve_io_type ---


def test_resolves_to_pickle_when_no_marks_present() -> None:
    """No record marks defaults to the Pickle IO handler."""
    actual = _resolve_io_type([])

    assert actual is Pickle


def test_resolves_to_pickle_when_pickle_mark_is_present() -> None:
    """A record mark naming 'pickle' resolves to the Pickle handler."""
    actual = _resolve_io_type([_mark("pickle")])

    assert actual is Pickle


def test_resolves_to_yaml_when_yaml_mark_is_present() -> None:
    """A record mark naming 'yaml' resolves to the Yaml handler."""
    actual = _resolve_io_type([_mark("yaml")])

    assert actual is Yaml


def test_resolves_to_json_when_json_mark_is_present() -> None:
    """A record mark naming 'json' resolves to the Json handler."""
    actual = _resolve_io_type([_mark("json")])

    assert actual is Json


def test_raises_when_mark_carries_no_args() -> None:
    """A bare record mark with no arguments raises DittoMarkHasNoIOType."""
    with pytest.raises(DittoMarkHasNoIOType):
        _resolve_io_type([_mark()])


def test_raises_when_mark_names_unregistered_io_type() -> None:
    """
    An unrecognised IO type name raises DittoMarkHasNoIOType rather than falling
    back silently.
    """
    with pytest.raises(DittoMarkHasNoIOType):
        _resolve_io_type([_mark("nonexistent")])


def test_raises_when_multiple_marks_are_present() -> None:
    """More than one record mark raises AdditionalMarkError."""
    with pytest.raises(AdditionalMarkError):
        _resolve_io_type([_mark("pickle"), _mark("json")])


# --- _snapshot_dir ---


def test_snapshot_dir_is_ditto_subdir_of_test_file() -> None:
    """Returns the .ditto directory that sits alongside the given test file."""
    test_path = Path("/project/tests/test_foo.py")

    actual = _snapshot_dir(test_path)

    assert actual == Path("/project/tests/.ditto")
