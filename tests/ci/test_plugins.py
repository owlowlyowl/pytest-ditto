import ditto


def test_plugin_load() -> None:
    print(ditto.io.IO_REGISTRY)
    assert ditto.io.IO_REGISTRY
