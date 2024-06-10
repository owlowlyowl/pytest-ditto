# from dataclasses import dataclass

import pytest

from ditto import Snapshot
from ditto import io
from ditto.exceptions import AdditionalMarkError, DittoMarkHasNoIOType


# @dataclass(frozen=True)
# class Parameters:
#     io_name: str


def _record_mark(node) -> pytest.Mark:
    marks = list(node.iter_markers(name="record"))
    if len(marks) > 1:
        raise AdditionalMarkError()
    return marks[0]


@pytest.fixture
def snapshot(request) -> Snapshot:

    # mark = _record_mark(request.node)
    marks = list(request.node.iter_markers(name="record"))
    match len(marks):
        case 0:
            io_type = io.Pickle
            parameters = {}
        case 1:
            if (io_type := io.get(marks[0].args[0])) is None:
                raise DittoMarkHasNoIOType()
            parameters = marks[0].kwargs
        case _:
            raise AdditionalMarkError()

    # TODO: parameterise the output path?
    path = request.path.parent / ".ditto"
    path.mkdir(exist_ok=True)

    return Snapshot(path=path, group_name=request.node.name, key={}, io=io_type)


def pytest_configure(config):
    # register an additional marker
    config.addinivalue_line("markers", "record(io): snapshot values")
