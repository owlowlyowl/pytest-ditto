"""Lazy recorder registry: names from metadata, imports on first lookup."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ditto import recorders
from ditto.exceptions import DittoRecorderLoadError
from ditto.recorders._plugins import RecorderRegistry

json_recorder = recorders.default()


def _ep(name: str, *, load_return=None, load_side_effect=None, dist="fake-dist"):
    ep = MagicMock()
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


def test_assigned_recorder_is_listed_alongside_entry_points() -> None:
    registry = RecorderRegistry([_ep("fmt", load_return=json_recorder)])

    registry["extra"] = json_recorder

    assert sorted(registry) == ["extra", "fmt"]
    assert len(registry) == 2


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
