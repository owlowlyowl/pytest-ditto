import ditto


def test_plugin_load() -> None:
    assert ditto.io.io_registry
