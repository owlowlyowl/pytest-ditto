from typing import Any

import pytest

from ditto.snapshot import Snapshot
from ditto import io


@pytest.fixture(scope="function")
def snapshot(request) -> Snapshot:

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

    # TODO: do i like this?
    # if io_name is None:
    #     pytest.fail("'record' is a required mark when using the 'snapshot' fixture.")

    path = request.path.parent / ".ditto"
    path.mkdir(exist_ok=True)

    # Get the snapshot identifier from the 'record' mark parameters (via kwargs) if it
    # exists; otherwise, use the test function name.
    identifier = parameters.get("identifier", request.node.name)

    return Snapshot(
        path=path,
        name=identifier,
        # record=True,
        io=io.get(io_name, default=io.PickleIO),
    )


def pytest_configure(config):
    # register an additional marker
    config.addinivalue_line("markers", "record(io): snapshot values")


# def pytest_runtest_setup(item):
#     # envnames = [mark.args[0] for mark in item.iter_markers(name="env")]
#     # if envnames:
#     #     if item.config.getoption("-E") not in envnames:
#     #         pytest.skip("test requires env in {!r}".format(envnames))
#     #
#     for mark in item.iter_markers(name="record"):
#         msg =f"recording: args={mark.args}; kwargs={mark.kwargs}"
#
#         path = item.path.parent / ".ditto"
#         name = mark.kwargs.get("identifier", mark.name)
#         identifier = mark.kwargs.get("identifier")
#         io_name = next(iter(mark.args))
#
#         snapshot = Snapshot(
#             path=path,
#             name=name,
#             record=False,
#             io=io.get(io_name, default=io.PickleIO),
#             identifier=identifier,
#         )
#         if not snapshot.filepath(identifier=identifier).exists():
#             pytest.skip(msg)
