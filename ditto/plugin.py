# from typing import Any
# from dataclasses import dataclass
from pathlib import Path

import pytest

from ditto import Snapshot
from ditto import io


# @dataclass
# class RecordMark:
#     io_name: str
#     parameters: dict[str, Any]
#
#
# def _parse_record_mark(mark) -> RecordMark:
#     return RecordMark(
#         io_name=mark.args[0] if mark.args else "pkl",
#         parameters=mark.kwargs,
#     )


class Snappy:
    def __init__(self, key):
        self.key = key

    def __call__(self, data):
        print(self.key, data)


@pytest.fixture
def snappy(request):

    name = request.node.name

    def _snappy(data, key):
        print(name, key, data)

        path = Path("c:/workspace/pytest-ditto") / ".snappy"
        path.mkdir(parents=True, exist_ok=True)

        fname = path / f"{name}@{key}.yml"
        if fname.exists():
            return io.Yaml.load(fname)
        else:
            io.Yaml.save(data, fname)
            return data

    return _snappy


# @pytest.fixture(scope="function")
@pytest.fixture
def snapshot(request) -> Snapshot:

    # record_markers = list(request.node.iter_markers(name="record"))
    # if len(record_markers) > 1:
    #     pytest.fail("Only one 'record' mark is allowed.")
    #
    # record_mark = _parse_record_mark(record_markers[0])

    io_name = None
    parameters = {}
    for mark in request.node.iter_markers(name="record"):
        if mark.args:
            if io_name is not None:
                pytest.fail("Only one 'record' mark is allowed.")
            io_name = mark.args[0]

        if mark.kwargs:
            parameters.update(mark.kwargs)

    io_name = io_name if io_name is not None else "pkl"

    # TODO: parameterise the output path
    path = request.path.parent / ".ditto"
    path.mkdir(exist_ok=True)

    # Get the snapshot identifier from the 'record' mark parameters (via kwargs) if it
    # exists; otherwise, use the test function name.
    # identifier = parameters.get("identifier", request.node.name)
    # identifier = record_mark.parameters.get("identifier", request.node.name)

    # if (
    #     request.node.name in request.config._ditto
    #     and identifier == request.node.name
    # ):
    #     request.config._ditto.remove(request.node.name)
    # else:
    #     pytest.fail(f"")

    # identifier = parameters.get("identifier", "")
    # identifier = f"@{identifier}" if identifier else identifier
    # key = f"{request.node.name}{identifier}"

    return Snapshot(
        path=path,
        group_name=request.node.name,
        key=parameters.get("key"),
        # name=identifier,
        # record=True,
        io=io.get(io_name, default=io.Pickle),
    )


def pytest_configure(config):
    # register an additional marker
    config.addinivalue_line("markers", "record(io): snapshot values")
