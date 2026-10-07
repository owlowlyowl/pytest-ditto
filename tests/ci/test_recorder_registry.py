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
from ditto.exceptions import DittoRecorderConflictError, DittoRecorderLoadError
from ditto.recorders import Recorder, RecorderRegistry

json_recorder = recorders.default()
_JSON = "ditto.recorders._json:json"


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


def _install_fake_plugin(root: Path) -> None:
    (root / "fakeplug_mod.py").write_text(
        "from ditto.recorders import Recorder\n"
        "recorder = Recorder(dumps=bytes, loads=bytes)\n"
    )
    dist_info = root / "fakeplug-0.1.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: fakeplug\nVersion: 0.1\n"
    )
    (dist_info / "entry_points.txt").write_text(
        "[ditto_recorders]\nfakeplug = fakeplug_mod:recorder\n"
    )


def test_only_first_use_imports_an_installed_recorder_plugin(
    tmp_path: Path,
) -> None:
    _install_fake_plugin(tmp_path)
    script = textwrap.dedent(
        """
        import sys
        import ditto
        from ditto import recorders

        assert "fakeplug" in recorders.RECORDER_REGISTRY
        assert recorders.RECORDER_REGISTRY.problems == ()
        assert ditto.fakeplug is not None
        assert "fakeplug_mod" not in sys.modules, "imported before first use"
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


# ── Plugin contract ────────────────────────────────────────────────────────────


NOT_A_RECORDER = object()
OTHER_RECORDER = Recorder(dumps=bytes, loads=bytes)


def test_problems_are_complete_before_any_recorder_loads(make_distribution) -> None:
    """A clash is found from metadata, even if no recorder involved is ever used."""
    core = make_distribution(
        "pytest-ditto", "2.0", {"ditto_recorders": {"json": _JSON}}
    )
    plugin = make_distribution(
        "plug", "1.0", {"ditto_recorders": {"json": "ditto_no_such_module:json"}}
    )
    registry = RecorderRegistry([*core, *plugin], [])

    (problem,) = registry.problems

    assert problem.names == {"json"}
    assert "plug 1.0, pytest-ditto 2.0" in problem.message


def test_looking_up_a_name_registered_twice_raises_naming_both_distributions(
    make_distribution,
) -> None:
    """A duplicated name is never silently resolved to one registration."""
    first = make_distribution("plug-a", "1.0", {"ditto_recorders": {"fmt": _JSON}})
    second = make_distribution("plug-b", "2.0", {"ditto_recorders": {"fmt": _JSON}})
    registry = RecorderRegistry([*first, *second], [])

    with pytest.raises(DittoRecorderConflictError, match="plug-a 1.0, plug-b 2.0"):
        registry["fmt"]


def test_a_conflict_leaves_other_recorders_usable(make_distribution) -> None:
    """Only the names a problem affects fail; the rest still load."""
    eps = make_distribution(
        "plug", "1.0", {"ditto_recorders": {"Bad-Name": _JSON, "good": _JSON}}
    )
    registry = RecorderRegistry(eps, [])

    actual = registry["good"]

    assert actual is json_recorder


def test_loading_recorders_never_changes_the_problems(make_distribution) -> None:
    """Problems depend on the registrations alone, not on what has loaded."""
    eps = make_distribution(
        "plug",
        "1.0",
        {"ditto_recorders": {"a": _JSON, "b": f"{__name__}:OTHER_RECORDER"}},
    )
    registry = RecorderRegistry(eps, [])

    registry["a"], registry["b"]

    assert registry.problems == ()


def test_one_recorder_under_two_names_is_not_a_conflict(make_distribution) -> None:
    """Two names for one recorder are two identifiers, so they never clash."""
    eps = make_distribution(
        "plug", "1.0", {"ditto_recorders": {"json": _JSON, "alias": _JSON}}
    )
    registry = RecorderRegistry(eps, [])

    assert registry["alias"] is registry["json"]
    assert registry.problems == ()


def test_entry_point_that_is_not_a_recorder_fails_to_load(make_distribution) -> None:
    """A value that is not a `Recorder` fails as a load error naming its type."""
    eps = make_distribution(
        "plug", "1.0", {"ditto_recorders": {"odd": f"{__name__}:NOT_A_RECORDER"}}
    )
    registry = RecorderRegistry(eps, [])

    with pytest.raises(DittoRecorderLoadError, match="is a object, not a"):
        registry["odd"]


def test_load_failure_from_a_1x_plugin_says_which_version_to_install(
    make_distribution,
) -> None:
    """A 1.x plugin that fails to load points at the 2.0-compatible release."""
    eps = make_distribution(
        "pytest-ditto-pandas",
        "0.1.1",
        {
            "ditto_recorders": {"pandas_csv": "ditto_no_such_module:csv"},
            "ditto_marks": {"pandas": "ditto_no_such_module:marks"},
        },
    )
    recorder_eps = [ep for ep in eps if ep.group == "ditto_recorders"]
    marks_eps = [ep for ep in eps if ep.group == "ditto_marks"]
    registry = RecorderRegistry(recorder_eps, marks_eps)

    with pytest.raises(DittoRecorderLoadError, match="pytest-ditto-pandas>=2.0"):
        registry["pandas_csv"]


def test_problems_list_each_1x_plugin_distribution(make_distribution) -> None:
    """A distribution registering `ditto_marks` is reported as a contract problem."""
    marks_eps = make_distribution(
        "pytest-ditto-pandas", "0.1.1", {"ditto_marks": {"pandas": "m:marks"}}
    )
    registry = RecorderRegistry([], marks_eps)

    actual = [problem.message for problem in registry.problems]

    expected = [
        "pytest-ditto-pandas 0.1.1 uses the 1.x plugin contract; install "
        "pytest-ditto-pandas>=2.0."
    ]
    assert actual == expected


# ── Registering recorders ──────────────────────────────────────────────────────


def test_registered_recorder_is_listed_after_entry_points() -> None:
    registry = RecorderRegistry([_ep("z_fmt", load_return=json_recorder)], [])

    registry.register("a_fmt", OTHER_RECORDER)

    assert list(registry) == ["z_fmt", "a_fmt"]
    assert registry["a_fmt"] is OTHER_RECORDER


def test_registering_an_installed_name_is_rejected_without_loading_it() -> None:
    """An installed recorder cannot be replaced, and is not imported to check."""
    ep = _ep("fmt", load_return=json_recorder, dist="plug")
    registry = RecorderRegistry([ep], [])

    with pytest.raises(
        DittoRecorderConflictError, match=r"'fmt' is registered more than once"
    ):
        registry.register("fmt", OTHER_RECORDER)

    ep.load.assert_not_called()
    assert registry["fmt"] is json_recorder


def test_registering_a_name_twice_is_rejected() -> None:
    registry = RecorderRegistry([], [])
    registry.register("fmt", json_recorder)

    with pytest.raises(DittoRecorderConflictError, match="more than once"):
        registry.register("fmt", OTHER_RECORDER)

    assert registry["fmt"] is json_recorder


@pytest.mark.parametrize(
    ("name", "message"),
    [
        pytest.param("Bad-Name", "is not valid", id="invalid"),
        pytest.param("snapshot", "shadows ditto.snapshot", id="reserved"),
        pytest.param("tabular", "ditto.tabular is ambiguous", id="namespace"),
    ],
)
def test_registering_a_name_that_breaks_the_contract_is_rejected(
    name: str, message: str
) -> None:
    registry = RecorderRegistry([_ep("tabular.csv", load_return=json_recorder)], [])

    with pytest.raises(DittoRecorderConflictError, match=message):
        registry.register(name, OTHER_RECORDER)

    assert name not in registry
    assert registry.problems == ()


def test_a_rejected_registration_leaves_earlier_ones_usable() -> None:
    """A later registration can never make an earlier one unusable."""
    registry = RecorderRegistry([], [])
    registry.register("tabular.csv", json_recorder)

    with pytest.raises(DittoRecorderConflictError):
        registry.register("tabular", OTHER_RECORDER)

    assert registry["tabular.csv"] is json_recorder


def test_registering_something_other_than_a_recorder_is_rejected() -> None:
    registry = RecorderRegistry([], [])

    with pytest.raises(TypeError, match="not a ditto.recorders.Recorder"):
        registry.register("fmt", NOT_A_RECORDER)

    assert "fmt" not in registry


def test_registering_in_a_copy_leaves_the_original_unchanged() -> None:
    registry = RecorderRegistry([], [])

    copied = copy(registry)
    copied.register("fmt", json_recorder)

    assert "fmt" in copied
    assert "fmt" not in registry
    registry.register("fmt", OTHER_RECORDER)


def test_a_path_based_plugin_fails_with_a_rebuild_hint(
    make_distribution, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plugin still building `Recorder(save=..., load=...)` says how to migrate."""
    (ep,) = make_distribution(
        "plug-old", "2.0.0b1", {"ditto_recorders": {"old": "oldplug_mod:recorder"}}
    )
    root = ep.dist.locate_file("")
    (root / "oldplug_mod.py").write_text(
        "from ditto.recorders import Recorder\n"
        "recorder = Recorder(save=print, load=print)\n"
    )
    monkeypatch.syspath_prepend(str(root))
    registry = RecorderRegistry([ep], [])

    with pytest.raises(DittoRecorderLoadError) as caught:
        registry["old"]

    message = str(caught.value)
    assert "'old' from plug-old 2.0.0b1" in message
    assert "Recorder(dumps=..., loads=...)" in message
    assert "recorder_from_files" in message


def test_other_type_errors_get_no_rebuild_hint(make_distribution) -> None:
    eps = make_distribution(
        "plug", "1.0", {"ditto_recorders": {"odd": f"{__name__}:NOT_A_RECORDER"}}
    )
    registry = RecorderRegistry(eps, [])

    with pytest.raises(DittoRecorderLoadError) as caught:
        registry["odd"]

    assert "recorder_from_files" not in str(caught.value)
