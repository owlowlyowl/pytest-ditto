import pytest

from ditto import Snapshot
from ditto import io
from ditto.exceptions import AdditionalMarkError, DittoMarkHasNoIOType


__all__ = ("snapshot",)


# TODO: parameterise the output path?
_DEFAULT_OUTPUT_DIR_NAME = ".ditto"


@pytest.fixture
def snapshot(request) -> Snapshot:

    marks = list(request.node.iter_markers(name="record"))
    match len(marks):
        # No ditto record mark exists, use defaults.
        case 0:
            io_type = io.Pickle
            parameters = {}

        # Ditto mark exists, get IO type and associated parameters from the mark.
        case 1:
            if (io_type := io.get(marks[0].args[0])) is None:
                raise DittoMarkHasNoIOType()
            parameters = marks[0].kwargs

        # More than one mark exists - not allowed.
        case _:
            raise AdditionalMarkError()

    path = request.path.parent / _DEFAULT_OUTPUT_DIR_NAME
    path.mkdir(exist_ok=True)

    return Snapshot(path=path, group_name=request.node.name, io=io_type)


def pytest_configure(config):
    # register an additional marker
    config.addinivalue_line("markers", "record(io): snapshot values")
