import pytest

import ditto
from ditto.io._plugins import (
    load_io_plugins,
    load_mark_plugins,
    IO_REGISTRY,
    MARK_REGISTRY,
)
from ditto.io._pickle import Pickle


@pytest.mark.parametrize("plugin_name", ("pickle", "yaml", "json"))
def test_builtin_io_plugin_is_present_in_registry_after_import(
    plugin_name: str,
) -> None:
    """Each built-in IO format is discoverable from the module-level IO_REGISTRY."""
    assert plugin_name in ditto.io.IO_REGISTRY


def test_load_io_plugins_discovers_all_builtin_handlers() -> None:
    """load_io_plugins returns a registry containing all three built-in IO handlers."""
    registry = load_io_plugins()

    assert set(registry.keys()) >= {"pickle", "yaml", "json"}


def test_mutating_loaded_io_plugins_does_not_affect_shared_registry() -> None:
    """Modifying a registry returned by load_io_plugins leaves IO_REGISTRY unchanged."""
    registry = load_io_plugins()

    registry["custom"] = Pickle

    assert "custom" not in IO_REGISTRY


def test_mutating_loaded_mark_plugins_does_not_affect_shared_registry() -> None:
    """
    Modifying a registry returned by load_mark_plugins leaves MARK_REGISTRY
    unchanged.
    """
    registry = load_mark_plugins()

    registry["custom"] = object()

    assert "custom" not in MARK_REGISTRY


def test_get_resolves_handler_from_supplied_registry() -> None:
    """io.get looks up a handler in a caller-supplied registry."""
    actual = ditto.io.get("custom", registry={"custom": Pickle})

    assert actual is Pickle


def test_get_returns_default_when_name_absent_from_registry() -> None:
    """io.get falls back to the default handler when the name is not in the registry."""
    actual = ditto.io.get("nonexistent", registry={}, default=Pickle)

    assert actual is Pickle


def test_register_adds_handler_to_supplied_registry_only() -> None:
    """
    io.register writes to the supplied registry and leaves the global registry
    unchanged.
    """
    isolated = {}

    ditto.io.register("custom", Pickle, registry=isolated)

    assert isolated["custom"] is Pickle
    assert "custom" not in ditto.io.IO_REGISTRY
