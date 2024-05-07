import pytest

from ditto import Snapshot
from ditto import io
from ditto.exceptions import AdditionalMarkError


@pytest.fixture
def snapshot(request) -> Snapshot:

    # TODO: sanitise the below mark parsing
    io_name = None
    parameters = {}
    for mark in request.node.iter_markers(name="record"):
        if mark.args:
            if io_name is not None:
                raise AdditionalMarkError()
            io_name = mark.args[0]

        if mark.kwargs:
            parameters.update(mark.kwargs)

    io_name = io_name if io_name is not None else "pkl"

    # TODO: parameterise the output path?
    path = request.path.parent / ".ditto"
    path.mkdir(exist_ok=True)

    return Snapshot(
        path=path,
        group_name=request.node.name,
        key=parameters.get("key"),
        io=io.get(io_name, default=io.Pickle),
    )


def pytest_configure(config):
    # register an additional marker
    config.addinivalue_line("markers", "record(io): snapshot values")
