import warnings
from unittest.mock import MagicMock, patch

import pytest

from ditto import recorders
from ditto.recorders._plugins import load_recorders, load_mark_plugins

pickle_recorder = recorders.default()


@pytest.mark.parametrize("recorder_name", ("pickle", "yaml", "json"))
def test_builtin_recorder_is_present_in_registry_after_import(
    recorder_name: str,
) -> None:
    """Each built-in recorder is discoverable from the module-level registry."""
    assert recorder_name in recorders.RECORDER_REGISTRY


def test_load_recorders_discovers_all_builtin_handlers() -> None:
    """load_recorders returns a registry containing all three built-in recorders."""
    registry = recorders.load_recorders()

    assert set(registry.keys()) >= {"pickle", "yaml", "json"}


def test_mutating_loaded_recorders_does_not_affect_shared_registry() -> None:
    """Mutating a load_recorders result leaves RECORDER_REGISTRY unchanged."""
    registry = recorders.load_recorders()

    registry["custom"] = pickle_recorder

    assert "custom" not in recorders.RECORDER_REGISTRY


def test_mutating_loaded_mark_plugins_does_not_affect_shared_registry() -> None:
    """Mutating a load_mark_plugins result leaves MARK_REGISTRY unchanged."""
    registry = recorders.load_mark_plugins()

    registry["custom"] = object()

    assert "custom" not in recorders.MARK_REGISTRY


def test_get_resolves_recorder_from_supplied_registry() -> None:
    """recorders.get looks up a recorder in a caller-supplied registry."""
    actual = recorders.get("custom", registry={"custom": pickle_recorder})

    assert actual is pickle_recorder


def test_get_returns_default_when_name_absent_from_registry() -> None:
    """recorders.get falls back to the default when the name is absent."""
    actual = recorders.get("nonexistent", registry={}, default=pickle_recorder)

    assert actual is pickle_recorder


def test_register_adds_recorder_to_supplied_registry_only() -> None:
    """recorders.register writes to the supplied registry, not the global one."""
    isolated = {}

    recorders.register("custom", pickle_recorder, registry=isolated)

    assert isolated["custom"] is pickle_recorder
    assert "custom" not in recorders.RECORDER_REGISTRY


def test_raises_when_accessing_nonexistent_plugin_mark() -> None:
    """Accessing an undefined attribute on the ditto module raises AttributeError."""
    import ditto

    with pytest.raises(AttributeError):
        _ = ditto.nonexistent_mark_xyz


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
    """A broken recorder entry point is skipped; a warning is emitted; good ones still load."""
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


def test_load_mark_plugins_skips_broken_entry_point_and_warns() -> None:
    """A broken mark entry point is skipped; a warning is emitted; good ones still load."""
    import ditto
    good_marks = ditto.pickle  # any real marks object

    good_factory = MagicMock(return_value=good_marks)
    good_ep = _make_ep("good", load_return=good_factory)
    bad_ep = _make_ep("bad", load_side_effect=AttributeError("no attr"))

    with patch("importlib.metadata.entry_points", return_value=[bad_ep, good_ep]):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = load_mark_plugins()

    assert "good" in result
    assert "bad" not in result
    assert len(caught) == 1
    assert "bad" in str(caught[0].message)
    assert "no attr" in str(caught[0].message)
