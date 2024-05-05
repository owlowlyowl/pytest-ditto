import pytest

from ditto import Snapshot
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

    # TODO: parameterise the output path
    path = request.path.parent / ".ditto"
    path.mkdir(exist_ok=True)

    # Get the snapshot identifier from the 'record' mark parameters (via kwargs) if it
    # exists; otherwise, use the test function name.
    identifier = parameters.get("identifier", request.node.name)

    return Snapshot(
        path=path,
        name=identifier,
        # record=True,
        io=io.get(io_name, default=io.Pickle),
    )


def pytest_configure(config):
    # register an additional marker
    config.addinivalue_line("markers", "record(io): snapshot values")


# def pytest_runtest_setup(item):
#     # TODO: potentially use to inspect markers, maybe store info on the item stash?


# def pytest_collection_modifyitems(config, items):
#     print(config, items)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item) -> None:
    """
    If the test contains a snapshot run test item again if recorded snapshot data
    doesn't exist. This will run the test against the recorded data.

    `pytest` hook to modify the test execution. This is a hookwrapper, which means the
    other `pytest_runtest_call` hooks will be called after this is executed.

    Called to run the test for test item (the call phase).

    The default implementation calls item.runtest().

    Reference
    ---------
    [1] https://docs.pytest.org/en/stable/reference/reference.html#pytest.hookspec.pytest_runtest_call
    """

    # TODO: further investigate use of `pytest_pyfunc_call` or components of the
    #  `pytest_runtest_protocol` that might provide a more elegant implementation.

    if (
        (snapshot := item.funcargs.get("snapshot")) is not None
        and isinstance(snapshot, Snapshot)
        and not snapshot.filepath().exists()
    ):
        _msg = (
            f"\nNo snapshot found for {item.nodeid}."
            f"\nRecoding new snapshot to {snapshot.filepath()!r}. "
            "\nTest will run again automatically to test with recorded snapshot."
        )
        print(_msg)
        item.runtest()

        # TODO: maybe fail the first test instead after all snapshots have been called
        #  and exist.

    outcome = yield

    # potential post-processing here

    return outcome
