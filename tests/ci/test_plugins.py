import pytest

from ditto import recorders

pickle_recorder = recorders.default()


@pytest.mark.parametrize("recorder_name", ("pickle", "yaml", "json"))
def test_builtin_recorder_is_present_in_registry_after_import(
    recorder_name: str,
) -> None:
    """Each built-in recorder is discoverable from the module-level RECORDER_REGISTRY."""
    assert recorder_name in recorders.RECORDER_REGISTRY


def test_load_recorders_discovers_all_builtin_handlers() -> None:
    """load_recorders returns a registry containing all three built-in recorders."""
    registry = recorders.load_recorders()

    assert set(registry.keys()) >= {"pickle", "yaml", "json"}


def test_mutating_loaded_recorders_does_not_affect_shared_registry() -> None:
    """Modifying a registry returned by load_recorders leaves RECORDER_REGISTRY unchanged."""
    registry = recorders.load_recorders()

    registry["custom"] = pickle_recorder

    assert "custom" not in recorders.RECORDER_REGISTRY


def test_mutating_loaded_mark_plugins_does_not_affect_shared_registry() -> None:
    """Modifying a registry returned by load_mark_plugins leaves MARK_REGISTRY unchanged."""
    registry = recorders.load_mark_plugins()

    registry["custom"] = object()

    assert "custom" not in recorders.MARK_REGISTRY


def test_get_resolves_recorder_from_supplied_registry() -> None:
    """recorders.get looks up a recorder in a caller-supplied registry."""
    actual = recorders.get("custom", registry={"custom": pickle_recorder})

    assert actual is pickle_recorder


def test_get_returns_default_when_name_absent_from_registry() -> None:
    """recorders.get falls back to the default recorder when the name is not in the registry."""
    actual = recorders.get("nonexistent", registry={}, default=pickle_recorder)

    assert actual is pickle_recorder


def test_register_adds_recorder_to_supplied_registry_only() -> None:
    """recorders.register writes to the supplied registry and leaves the global registry unchanged."""
    isolated = {}

    recorders.register("custom", pickle_recorder, registry=isolated)

    assert isolated["custom"] is pickle_recorder
    assert "custom" not in recorders.RECORDER_REGISTRY
