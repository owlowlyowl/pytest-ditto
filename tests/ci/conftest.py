import shutil

import pytest

pytest_plugins = ["pytester"]


@pytest.fixture(scope="function")
def tmp_dir(tmp_path_factory, request):
    tmp = tmp_path_factory.mktemp(request.node.name)
    yield tmp
    shutil.rmtree(tmp)
