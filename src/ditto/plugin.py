from pathlib import Path

import pytest

from ditto import Snapshot
from ditto import io
from ditto.io._plugins import IO_REGISTRY
from ditto.exceptions import AdditionalMarkError, DittoMarkHasNoIOType


__all__ = ("snapshot",)


_DEFAULT_OUTPUT_DIR_NAME = ".ditto"


def _resolve_io_type(marks: list) -> type:
    """
    Resolve the IO handler class from a list of pytest marks.

    Parameters
    ----------
    marks : list
        Collected pytest marks named `record` from the test node.

    Returns
    -------
    type
        The IO handler class corresponding to the mark, or `Pickle` when
        no mark is present.

    Raises
    ------
    AdditionalMarkError
        If more than one `record` mark is present on the test.
    DittoMarkHasNoIOType
        If the mark carries no arguments or names an IO type that is not
        registered — making unknown format strings an explicit error rather
        than a silent fallback to Pickle.
    """
    match len(marks):
        case 0:
            return io.Pickle
        case 1:
            if not marks[0].args or marks[0].args[0] not in IO_REGISTRY:
                raise DittoMarkHasNoIOType()
            return IO_REGISTRY[marks[0].args[0]]
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
    io_type = _resolve_io_type(marks)
    path = _snapshot_dir(request.path)
    path.mkdir(exist_ok=True)
    return Snapshot(path=path, group_name=request.node.name, io=io_type)


def pytest_configure(config):
    config.addinivalue_line("markers", "record(io): snapshot values")
