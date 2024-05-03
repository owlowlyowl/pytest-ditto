# from pathlib import Path
from typing import Any

import pytest

from ditto.snapshot import Snapshot
from ditto import io


# @pytest.fixture(scope="session")
# def snapshot_data_path() -> Path:
#     path = Path(__file__).parent / "tmp"
#     path.mkdir(parents=True, exist_ok=True)
#     return path
#


@pytest.fixture(scope="function")
def snapshot(request) -> Snapshot:
    io_map: dict[str, Any] = {
        "pkl": io.PickleIO,
        "json": io.JsonIO,
        "yaml": io.YamlIO,
        "pandas_parquet": io.PandasParquetIO,
    }

    io_name = None
    for mark in request.node.iter_markers(name="record"):
        if mark.args:
            if io_name is not None:
                pytest.fail("Only one 'record' mark is allowed.")
            io_name = mark.args[0]

    # TODO: do i like this?
    # if io_name is None:
    #     pytest.fail("'record' is a required mark when using the 'snapshot' fixture.")

    path = request.path.parent / ".ditto"
    path.mkdir(exist_ok=True)

    return Snapshot(
        path=path,
        name=request.node.name,
        record=True,
        io=io_map.get(io_name, io.PickleIO),
    )


#
# @pytest.hookimpl(tryfirst=True)
# def pytest_fixture_setup(fixturedef, request):
#     print('Fixture setup: ', fixturedef.argname)
#     print(fixturedef)
#
#
# def pytest_addoption(parser):
#     parser.addoption(
#         "-E",
#         action="store",
#         metavar="NAME",
#         help="only run tests matching the environment NAME.",
#     )
#     parser.addoption(
#         "-R",
#         action="store",
#         metavar="RECORD",
#         help="only run tests matching the environment NAME.",
#     )
#
#
def pytest_configure(config):
    # register an additional marker
    # config.addinivalue_line(
    #     "markers", "env(name): mark test to run only on named environment"
    # )
    config.addinivalue_line("markers", "record(io): snapshot values")


# def pytest_runtest_setup(item):
#     envnames = [mark.args[0] for mark in item.iter_markers(name="env")]
#     if envnames:
#         if item.config.getoption("-E") not in envnames:
#             pytest.skip("test requires env in {!r}".format(envnames))
#
#     for mark in item.iter_markers(name="record"):
#         msg =f"recording: args={mark.args}; kwargs={mark.kwargs}"
#         # pytest.skip(msg)
#         print(msg)
