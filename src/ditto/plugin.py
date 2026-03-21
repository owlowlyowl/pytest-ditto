from pathlib import Path

import pytest

from ditto import Snapshot
from ditto.recorders._pickle import pickle as _default_recorder
from ditto.recorders._plugins import RECORDER_REGISTRY
from ditto.recorders._protocol import Recorder
from ditto.exceptions import AdditionalMarkError, DittoMarkHasNoIOType


__all__ = ("snapshot",)


_DEFAULT_OUTPUT_DIR_NAME = ".ditto"


def _resolve_recorder(marks: list) -> Recorder:
    """
    Resolve the recorder from a list of pytest marks.

    Parameters
    ----------
    marks : list
        Collected pytest marks named `record` from the test node.

    Returns
    -------
    Recorder
        The recorder corresponding to the mark, or the pickle recorder when
        no mark is present.

    Raises
    ------
    AdditionalMarkError
        If more than one `record` mark is present on the test.
    DittoMarkHasNoIOType
        If the mark carries no arguments or names a recorder that is not
        registered — making unknown format strings an explicit error rather
        than a silent fallback to pickle.
    """
    match len(marks):
        case 0:
            return _default_recorder
        case 1:
            if not marks[0].args or marks[0].args[0] not in RECORDER_REGISTRY:
                raise DittoMarkHasNoIOType()
            return RECORDER_REGISTRY[marks[0].args[0]]
        case _:
            raise AdditionalMarkError()


def _snapshot_dir(test_path: Path) -> Path:
    """
    Return the `.ditto` directory path adjacent to the given test file.

    Parameters
    ----------
    test_path : Path
        Path to the test file.

    Returns
    -------
    Path
        The `.ditto` directory that sits alongside the test file.
    """
    return test_path.parent / _DEFAULT_OUTPUT_DIR_NAME


@pytest.fixture
def snapshot(request) -> Snapshot:
    marks = list(request.node.iter_markers(name="record"))
    recorder = _resolve_recorder(marks)
    path = _snapshot_dir(request.path)
    path.mkdir(exist_ok=True)
    return Snapshot(path=path, group_name=request.node.name, recorder=recorder)


def pytest_configure(config):
    config.addinivalue_line("markers", "record(recorder): snapshot values")
