import pytest

import ditto


@pytest.mark.parametrize(
    "plugin_name",
    ("pickle", "yaml", "json", "pandas_parquet"),
)
def test_plugin_load(plugin_name: str) -> None:
    print(ditto.io.IO_REGISTRY)
    assert ditto.io.IO_REGISTRY
    assert plugin_name in ditto.io.IO_REGISTRY
    
