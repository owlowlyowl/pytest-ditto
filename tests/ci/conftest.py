import importlib.metadata
import shutil
from importlib.metadata import EntryPoint

import pytest

pytest_plugins = ["pytester"]


@pytest.fixture(scope="function")
def tmp_dir(tmp_path_factory, request):
    tmp = tmp_path_factory.mktemp(request.node.name)
    yield tmp
    shutil.rmtree(tmp)


@pytest.fixture
def make_distribution(tmp_path):
    """Return a factory that writes an installed distribution's metadata.

    `make_distribution(name, version, entry_points)` writes a `.dist-info`
    directory in its own folder under `tmp_path` and returns the distribution's
    entry points, each bound to the distribution (so `ep.dist.name` and
    `ep.dist.version` are real).
    `entry_points` maps a group to `{entry-point name: value}`.
    """

    def make(
        name: str, version: str, entry_points: dict[str, dict[str, str]]
    ) -> list[EntryPoint]:
        # One directory per distribution: importlib.metadata caches a directory's
        # listing by its mtime, which may not change between two quick writes.
        root = tmp_path / f"{name}-{version}"
        dist_info = root / f"{name.replace('-', '_')}-{version}.dist-info"
        dist_info.mkdir(parents=True)
        (dist_info / "METADATA").write_text(
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
        )
        (dist_info / "entry_points.txt").write_text(
            "".join(
                f"[{group}]\n" + "".join(f"{k} = {v}\n" for k, v in eps.items())
                for group, eps in entry_points.items()
            )
        )
        (dist,) = [
            d
            for d in importlib.metadata.distributions(path=[str(root)])
            if d.metadata["Name"] == name
        ]
        return list(dist.entry_points)

    return make
