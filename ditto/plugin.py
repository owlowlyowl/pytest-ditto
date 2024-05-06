# from typing import Any
# from dataclasses import dataclass

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
        name=request.node.name,
        identifier=parameters.get("identifier"),
        # name=identifier,
        # record=True,
        io=io.get(io_name, default=io.Pickle),
        # io=io.get(record_mark.io_name, default=io.Pickle),
    )

    # if key not in request.config._ditto_snapshots:
    #     snapshot = Snapshot(
    #         path=path,
    #         name=request.node.name,
    #         identifier=parameters.get("identifier"),
    #         # name=identifier,
    #         # record=True,
    #         io=io.get(io_name, default=io.Pickle),
    #         # io=io.get(record_mark.io_name, default=io.Pickle),
    #     )
    #     snapshot.add_key(key)
    #     request.config._ditto_snapshots[key] = snapshot
    #     return request.config._ditto_snapshots[key]
    #
    # if request.config._ditto_snapshots[key].is_existing_reference():
    #     pytest.fail(f"more than one snapshot with same {identifier=} found")


def pytest_configure(config):
    # register an additional marker
    config.addinivalue_line("markers", "record(io): snapshot values")


# def pytest_runtest_setup(item):
#     # TODO: potentially use to inspect markers, maybe store info on the item stash?


def pytest_collection_modifyitems(config, items):
    print(config, items)
    config._ditto = [item.name for item in items]


# @pytest.hookimpl(hookwrapper=True)
# def pytest_runtest_call(item) -> None:
#     """
#     If the test contains a snapshot run test item again if recorded snapshot data
#     doesn't exist. This will run the test against the recorded data.
#
#     `pytest` hook to modify the test execution. This is a hookwrapper, which means the
#     other `pytest_runtest_call` hooks will be called after this is executed.
#
#     Called to run the test for test item (the call phase).
#
#     The default implementation calls item.runtest().
#
#     Reference
#     ---------
#     [1] https://docs.pytest.org/en/stable/reference/reference.html#pytest.hookspec.pytest_runtest_call
#     """
#
#     # TODO: further investigate use of `pytest_pyfunc_call` or components of the
#     #  `pytest_runtest_protocol` that might provide a more elegant implementation.
#
#     if (
#         (snapshot := item.funcargs.get("snapshot")) is not None
#         and isinstance(snapshot, Snapshot)
#         and not snapshot.filepath().exists()
#     ):
#         _msg = (
#             f"\nNo snapshot found for {item.nodeid}."
#             f"\nRecoding new snapshot to {snapshot.filepath()!r}. "
#             "\nTest will run again automatically to test with recorded snapshot."
#         )
#         print(_msg)
#         item.runtest()
#
#         # TODO: maybe fail the first test instead after all snapshots have been called
#         #  and exist.
#
#     outcome = yield
#
#     # potential post-processing here
#
#     return outcome
#


@pytest.hookimpl(tryfirst=True)
def pytest_fixture_setup(fixturedef, request):
    # If the fixturedef contains a reference to the snapshot fixture, we need to modify
    # the snapshot identifier so that downstream uses of this fixture don't result in
    # snapshot creating a snapshot file for the data wit the same name as the one from
    # the test.

    if "snapshot" in fixturedef.argnames:
        _msg = (
            "The `snapshot` fixture cannot be used from within other fixtures.\n"
            f"Problem fixture is {fixturedef.argname!r} from {fixturedef.baseid}."
        )
        pytest.fail(_msg)
    # pass


def pytest_sessionstart(session) -> None:
    session.config._ditto = []
    session.config._ditto_snapshots = {}
    # pass
