import warnings
from importlib.metadata import EntryPoint
from unittest.mock import MagicMock, patch

import pytest

from ditto import recorders
from ditto.exceptions import DittoRecorderLoadError, DittoUnknownRecorderError
from ditto.recorders import _plugins
from ditto.recorders._plugins import RecorderRegistry, load_recorders

json_recorder = recorders.default()


@pytest.mark.parametrize("recorder_name", ("yaml", "json"))
def test_builtin_recorder_is_present_in_registry_after_import(
    recorder_name: str,
) -> None:
    """Each built-in recorder is discoverable from the module-level registry."""
    assert recorder_name in recorders.RECORDER_REGISTRY


def test_load_recorders_discovers_all_builtin_handlers() -> None:
    """load_recorders returns both built-in recorders."""
    registry = recorders.load_recorders()

    assert set(registry.keys()) >= {"yaml", "json"}
    assert "pickle" not in registry


def test_mutating_loaded_recorders_does_not_affect_shared_registry() -> None:
    """Mutating a load_recorders result leaves RECORDER_REGISTRY unchanged."""
    registry = recorders.load_recorders()

    registry["custom"] = json_recorder

    assert "custom" not in recorders.RECORDER_REGISTRY


def test_get_resolves_recorder_from_supplied_registry() -> None:
    """recorders.get looks up a recorder in a caller-supplied registry."""
    actual = recorders.get("custom", registry={"custom": json_recorder})

    assert actual is json_recorder


def test_get_returns_explicit_fallback_when_name_absent_from_registry() -> None:
    """recorders.get returns a deliberately supplied fallback when absent."""
    actual = recorders.get("nonexistent", registry={}, fallback=json_recorder)

    assert actual is json_recorder


def test_get_raises_when_name_absent_without_explicit_fallback() -> None:
    """recorders.get never silently selects the default for an unknown name."""
    with pytest.raises(DittoUnknownRecorderError, match="nonexistent"):
        recorders.get("nonexistent", registry={})


def test_register_adds_recorder_to_supplied_registry_only() -> None:
    """recorders.register writes to the supplied registry, not the global one."""
    isolated = {}

    recorders.register("custom", json_recorder, registry=isolated)

    assert isolated["custom"] is json_recorder
    assert "custom" not in recorders.RECORDER_REGISTRY


def test_raises_when_accessing_nonexistent_plugin_mark() -> None:
    """Accessing an undefined attribute on the ditto module raises AttributeError."""
    import ditto

    with pytest.raises(AttributeError):
        _ = ditto.nonexistent_mark_xyz


# ── Marks derived from recorder names ─────────────────────────────────────────


def _unloadable(name: str) -> EntryPoint:
    """Build an entry point whose target cannot be imported."""
    return EntryPoint(name=name, value="ditto_no_such_module:recorder", group="")


@pytest.fixture()
def plugin_names(monkeypatch: pytest.MonkeyPatch) -> RecorderRegistry:
    """Serve marks from a registry of plugin names that fail if ever loaded."""
    registry = RecorderRegistry([
        _unloadable("custom"),
        _unloadable("tabular.csv"),
        _unloadable("tabular.parquet"),
    ])
    monkeypatch.setattr(_plugins, "RECORDER_REGISTRY", registry)
    return registry


def test_bare_recorder_name_derives_top_level_mark(plugin_names) -> None:
    """A bare recorder name `fmt` is exposed as `ditto.fmt`."""
    import ditto

    assert ditto.custom == pytest.mark.record("custom")


def test_dotted_recorder_name_derives_namespaced_mark(plugin_names) -> None:
    """A dotted recorder name `ns.fmt` is exposed as `ditto.ns.fmt`."""
    import ditto

    assert ditto.tabular.csv == pytest.mark.record("tabular.csv")
    assert ditto.tabular.parquet == pytest.mark.record("tabular.parquet")


def test_resolving_marks_does_not_load_plugins(plugin_names) -> None:
    """Deriving marks reads only the registered names, never the recorders."""
    import ditto

    _ = ditto.custom, ditto.tabular.csv

    # Still an unloaded entry point: the first real lookup is what fails.
    with pytest.raises(DittoRecorderLoadError):
        recorders.get("tabular.csv", registry=plugin_names)


def test_unknown_format_in_namespace_lists_available_formats(plugin_names) -> None:
    """A typo under a namespace names the formats that do exist."""
    import ditto

    with pytest.raises(AttributeError, match="'cvs'.*available: csv, parquet"):
        _ = ditto.tabular.cvs


def test_namespace_is_not_itself_a_mark(plugin_names) -> None:
    """A namespace names no recorder, so it exposes its formats, not a mark."""
    import ditto

    assert not isinstance(ditto.tabular, pytest.MarkDecorator)
    assert dir(ditto.tabular) == ["csv", "parquet"]


def test_recorder_registered_at_runtime_derives_mark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recorders added to the registry at runtime get marks too."""
    import ditto

    monkeypatch.setitem(recorders.RECORDER_REGISTRY, "runtime.fmt", json_recorder)

    assert ditto.runtime.fmt == pytest.mark.record("runtime.fmt")


# ── Broken entry point resilience ─────────────────────────────────────────────


def _make_ep(name: str, load_side_effect=None, load_return=None):
    """Build a fake entry point mock."""
    ep = MagicMock()
    ep.name = name
    if load_side_effect is not None:
        ep.load.side_effect = load_side_effect
    else:
        ep.load.return_value = load_return
    return ep


def test_load_recorders_skips_broken_entry_point_and_warns() -> None:
    """A broken recorder entry point is skipped; a warning is emitted; good ones
    still load."""
    good_recorder = recorders.default()
    good_ep = _make_ep("good", load_return=good_recorder)
    bad_ep = _make_ep("bad", load_side_effect=ImportError("missing lib"))

    with patch("importlib.metadata.entry_points", return_value=[bad_ep, good_ep]):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = load_recorders()

    assert "good" in result
    assert "bad" not in result
    assert len(caught) == 1
    assert "bad" in str(caught[0].message)
    assert "missing lib" in str(caught[0].message)
