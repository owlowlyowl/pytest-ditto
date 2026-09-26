"""Lazy recorder registry: names from metadata, imports on first lookup."""

import os
import subprocess
import sys
import textwrap
from copy import copy
from importlib.metadata import EntryPoint
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ditto import recorders
from ditto.exceptions import DittoRecorderLoadError
from ditto.recorders._plugins import RecorderRegistry

json_recorder = recorders.default()


def _ep(name: str, *, load_return=None, load_side_effect=None, dist="fake-dist"):
    ep = MagicMock(spec=EntryPoint)
    ep.name = name
    ep.dist.name = dist
    if load_side_effect is not None:
        ep.load.side_effect = load_side_effect
    else:
        ep.load.return_value = load_return
    return ep


def test_membership_and_iteration_do_not_load_entry_points() -> None:
    ep = _ep("fmt", load_return=json_recorder)
    registry = RecorderRegistry([ep])

    assert "fmt" in registry
    assert list(registry) == ["fmt"]
    assert len(registry) == 1
    ep.load.assert_not_called()


def test_lookup_loads_entry_point_once() -> None:
    ep = _ep("fmt", load_return=json_recorder)
    registry = RecorderRegistry([ep])

    assert registry["fmt"] is json_recorder
    assert registry["fmt"] is json_recorder
    ep.load.assert_called_once()


def test_lookup_of_unknown_name_raises_key_error() -> None:
    registry = RecorderRegistry([])

    with pytest.raises(KeyError):
        registry["missing"]


def test_broken_entry_point_fails_only_when_looked_up() -> None:
    good = _ep("good", load_return=json_recorder)
    bad = _ep("bad", load_side_effect=ImportError("missing lib"), dist="pkg-bad")
    registry = RecorderRegistry([good, bad])

    assert registry["good"] is json_recorder
    with pytest.raises(
        DittoRecorderLoadError, match=r"'bad' from pkg-bad.*missing lib"
    ):
        registry["bad"]


def test_assigned_recorder_overrides_entry_point_without_loading_it() -> None:
    ep = _ep("fmt", load_return=object())
    registry = RecorderRegistry([ep])

    registry["fmt"] = json_recorder

    assert registry["fmt"] is json_recorder
    ep.load.assert_not_called()


def test_load_error_without_distribution_preserves_cause() -> None:
    ep = EntryPoint(
        name="broken",
        value="_ditto_missing_test_plugin:recorder",
        group="ditto_recorders",
    )
    registry = RecorderRegistry([ep])

    with pytest.raises(
        DittoRecorderLoadError, match="'broken' from an unknown distribution"
    ) as caught:
        registry["broken"]

    assert isinstance(caught.value.__cause__, ModuleNotFoundError)
    assert caught.value.__cause__.name == "_ditto_missing_test_plugin"


def test_fallback_only_applies_to_absent_names() -> None:
    ep = _ep("broken", load_side_effect=ImportError("missing lib"))
    registry = RecorderRegistry([ep])

    assert recorders.get("missing", registry, fallback=json_recorder) is json_recorder
    ep.load.assert_not_called()
    with pytest.raises(DittoRecorderLoadError, match="missing lib"):
        recorders.get("broken", registry, fallback=json_recorder)


def test_shallow_copy_preserves_cached_recorders_and_loads_independently() -> None:
    loaded = _ep("loaded", load_return=json_recorder)
    pending = _ep("pending", load_return=json_recorder)
    registry = RecorderRegistry([loaded, pending])
    assert registry["loaded"] is json_recorder

    copied = copy(registry)

    assert copied is not registry
    assert list(copied) == list(registry)
    assert copied["loaded"] is registry["loaded"]
    loaded.load.assert_called_once()
    pending.load.assert_not_called()
    assert copied["pending"] is json_recorder
    pending.load.assert_called_once()
    assert registry["pending"] is json_recorder
    assert pending.load.call_count == 2
    assert copied["pending"] is registry["pending"]
    assert pending.load.call_count == 2


def test_shallow_copy_mutations_do_not_change_original() -> None:
    ep = _ep("broken", load_side_effect=ImportError("missing lib"))
    registry = RecorderRegistry([ep])
    registry["assigned"] = json_recorder
    copied = copy(registry)
    replacement = recorders.Recorder(
        "replacement", json_recorder.save, json_recorder.load
    )

    copied["assigned"] = replacement
    copied["extra"] = replacement
    del copied["broken"]
    assert registry["assigned"] is json_recorder
    assert list(registry) == ["broken", "assigned"]
    assert list(copied) == ["assigned", "extra"]

    registry["original_only"] = json_recorder
    assert "original_only" not in copied
    copied.clear()
    assert len(copied) == 0
    assert list(registry) == ["broken", "assigned", "original_only"]
    ep.load.assert_not_called()


def test_assigned_recorder_is_listed_alongside_entry_points() -> None:
    registry = RecorderRegistry([_ep("fmt", load_return=json_recorder)])

    registry["extra"] = json_recorder

    assert sorted(registry) == ["extra", "fmt"]
    assert len(registry) == 2


def test_iteration_preserves_order_across_loading_and_overrides() -> None:
    first = _ep("z_first", load_return=json_recorder)
    second = _ep("a_second", load_return=json_recorder)
    registry = RecorderRegistry([first, second])
    registry["z_extra"] = json_recorder
    registry["a_extra"] = json_recorder

    assert registry["a_second"] is json_recorder
    registry["z_first"] = json_recorder
    registry["z_extra"] = json_recorder

    assert list(registry) == ["z_first", "a_second", "z_extra", "a_extra"]
    assert len(registry) == 4
    first.load.assert_not_called()
    second.load.assert_called_once()

    del registry["z_first"]
    registry["z_first"] = json_recorder
    assert list(registry) == ["a_second", "z_extra", "a_extra", "z_first"]
    assert len(registry) == 4


def test_clear_removes_all_registrations_without_loading_plugins() -> None:
    loaded = _ep("loaded", load_return=json_recorder)
    overridden = _ep("overridden", load_side_effect=ImportError("missing lib"))
    broken = _ep("broken", load_side_effect=ImportError("missing lib"))
    registry = RecorderRegistry([loaded, overridden, broken])
    assert registry["loaded"] is json_recorder
    registry["overridden"] = json_recorder
    registry["extra"] = json_recorder

    registry.clear()
    registry.clear()

    assert list(registry) == []
    assert len(registry) == 0
    for name in ("loaded", "overridden", "broken", "extra"):
        assert name not in registry
        with pytest.raises(KeyError):
            registry[name]
    loaded.load.assert_called_once()
    overridden.load.assert_not_called()
    broken.load.assert_not_called()


def test_deleting_a_broken_entry_point_does_not_load_it() -> None:
    ep = _ep("broken", load_side_effect=ImportError("missing lib"))
    registry = RecorderRegistry([ep])

    del registry["broken"]

    assert "broken" not in registry
    ep.load.assert_not_called()


def test_deleting_a_name_removes_it_entirely() -> None:
    registry = RecorderRegistry([_ep("fmt", load_return=json_recorder)])
    registry["fmt"] = json_recorder

    del registry["fmt"]

    assert "fmt" not in registry
    with pytest.raises(KeyError):
        del registry["fmt"]


def test_monkeypatched_recorder_is_removed_on_undo() -> None:
    registry = RecorderRegistry([])
    mp = pytest.MonkeyPatch()

    mp.setitem(registry, "temp", json_recorder)
    assert registry["temp"] is json_recorder
    mp.undo()

    assert "temp" not in registry


@pytest.mark.parametrize("operation", ["setitem", "delitem"])
def test_monkeypatch_loads_and_restores_existing_recorder(operation: str) -> None:
    ep = _ep("fmt", load_return=json_recorder)
    registry = RecorderRegistry([ep])
    replacement = recorders.Recorder(
        "replacement", json_recorder.save, json_recorder.load
    )

    with pytest.MonkeyPatch.context() as mp:
        if operation == "setitem":
            mp.setitem(registry, "fmt", replacement)
            assert registry["fmt"] is replacement
        else:
            mp.delitem(registry, "fmt")
            assert "fmt" not in registry
        ep.load.assert_called_once()

    assert registry["fmt"] is json_recorder
    ep.load.assert_called_once()


@pytest.mark.parametrize("operation", ["setitem", "delitem"])
def test_monkeypatch_cannot_replace_or_remove_broken_entry_point(
    operation: str,
) -> None:
    ep = _ep("broken", load_side_effect=ImportError("missing lib"))
    registry = RecorderRegistry([ep])

    with pytest.MonkeyPatch.context() as mp:
        with pytest.raises(DittoRecorderLoadError, match="missing lib"):
            if operation == "setitem":
                mp.setitem(registry, "broken", json_recorder)
            else:
                mp.delitem(registry, "broken")

    assert "broken" in registry
    ep.load.assert_called_once()
    recorders.register("broken", json_recorder, registry=registry)
    assert registry["broken"] is json_recorder
    ep.load.assert_called_once()


def _install_fake_plugin(root: Path) -> None:
    (root / "fakeplug_mod.py").write_text("recorder = object()\n")
    dist_info = root / "fakeplug-0.1.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: fakeplug\nVersion: 0.1\n"
    )
    (dist_info / "entry_points.txt").write_text(
        "[ditto_recorders]\nfakeplug = fakeplug_mod:recorder\n"
    )


def test_import_ditto_does_not_import_installed_recorder_plugins(
    tmp_path: Path,
) -> None:
    _install_fake_plugin(tmp_path)
    script = textwrap.dedent(
        """
        import sys
        import ditto
        from ditto import recorders

        assert "fakeplug" in recorders.RECORDER_REGISTRY
        assert "fakeplug_mod" not in sys.modules, "imported at import ditto"
        recorders.get("fakeplug")
        assert "fakeplug_mod" in sys.modules, "not imported on first use"
        """
    )
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            filter(None, [str(tmp_path), os.environ.get("PYTHONPATH")])
        ),
    }

    result = subprocess.run(
        [sys.executable, "-c", script], env=env, capture_output=True, text=True
    )

    assert result.returncode == 0, result.stderr
