"""Lazy backend registry: schemes from metadata, imports on first lookup."""

import os
import subprocess
import sys
import textwrap
from collections.abc import MutableMapping
from importlib.metadata import EntryPoint
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ditto.backends import BackendRegistry
from ditto.backends._contract import find_scheme_problems
from ditto._entry_points import Distribution, Registration
from ditto.exceptions import DittoBackendConflictError, DittoBackendLoadError


def dict_factory(uri: str, **opts: object) -> MutableMapping[str, bytes]:
    return {}


def other_factory(uri: str, **opts: object) -> MutableMapping[str, bytes]:
    return {}


_FACTORY = f"{__name__}:dict_factory"


def _ep(name: str, *, load_return=None, load_side_effect=None, dist="fake-dist"):
    ep = MagicMock(spec=EntryPoint)
    ep.name = name
    ep.value = f"{dist}_mod:factory"
    ep.dist.name = dist
    ep.dist.version = ""
    if load_side_effect is not None:
        ep.load.side_effect = load_side_effect
    else:
        ep.load.return_value = load_return
    return ep


# ── Discovery and loading ──────────────────────────────────────────────────────


def test_membership_and_iteration_do_not_load_entry_points() -> None:
    ep = _ep("demo", load_return=dict_factory)
    registry = BackendRegistry([ep])

    assert "demo" in registry
    assert list(registry) == ["demo"]
    assert len(registry) == 1
    ep.load.assert_not_called()


def test_lookup_loads_entry_point_once() -> None:
    ep = _ep("demo", load_return=dict_factory)
    registry = BackendRegistry([ep])

    assert registry["demo"] is dict_factory
    assert registry["demo"] is dict_factory
    ep.load.assert_called_once()


def test_lookup_of_unknown_scheme_raises_key_error() -> None:
    registry = BackendRegistry([])

    assert "missing" not in registry
    with pytest.raises(KeyError):
        registry["missing"]


def test_broken_entry_point_fails_only_when_looked_up() -> None:
    good = _ep("good", load_return=dict_factory)
    bad = _ep("bad", load_side_effect=ImportError("missing lib"), dist="pkg-bad")
    registry = BackendRegistry([good, bad])

    assert registry["good"] is dict_factory
    with pytest.raises(DittoBackendLoadError, match=r"'bad' from pkg-bad.*missing lib"):
        registry["bad"]


def test_load_error_names_the_distribution_and_preserves_cause() -> None:
    ep = EntryPoint(
        name="broken",
        value="_ditto_missing_test_backend:factory",
        group="ditto_backends",
    )
    registry = BackendRegistry([ep])

    with pytest.raises(
        DittoBackendLoadError, match="'broken' from an unknown distribution"
    ) as caught:
        registry["broken"]

    assert isinstance(caught.value.__cause__, ModuleNotFoundError)
    assert caught.value.__cause__.name == "_ditto_missing_test_backend"


def test_entry_point_that_is_not_callable_fails_to_load() -> None:
    registry = BackendRegistry([_ep("demo", load_return=object())])

    with pytest.raises(DittoBackendLoadError, match="not callable") as caught:
        registry["demo"]

    assert isinstance(caught.value.__cause__, TypeError)


def _install_fake_backend(root: Path) -> None:
    (root / "fakebackend_mod.py").write_text(
        "def factory(uri, **opts):\n    return {}\n"
    )
    dist_info = root / "fakebackend-0.1.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: fakebackend\nVersion: 0.1\n"
    )
    (dist_info / "entry_points.txt").write_text(
        "[ditto_backends]\nfakescheme = fakebackend_mod:factory\n"
    )


def test_only_first_use_imports_an_installed_backend_plugin(tmp_path: Path) -> None:
    _install_fake_backend(tmp_path)
    script = textwrap.dedent(
        """
        import sys
        import ditto.plugin
        from ditto.backends import BACKEND_REGISTRY

        assert "fakescheme" in BACKEND_REGISTRY
        assert BACKEND_REGISTRY.problems == ()
        assert "fakebackend_mod" not in sys.modules, "imported before first use"
        BACKEND_REGISTRY["fakescheme"]
        assert "fakebackend_mod" in sys.modules, "not imported on first use"
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


def test_problems_are_complete_before_any_backend_loads(make_distribution) -> None:
    first = make_distribution("plug-a", "1.0", {"ditto_backends": {"demo": _FACTORY}})
    second = make_distribution("plug-b", "2.0", {"ditto_backends": {"demo": _FACTORY}})

    registry = BackendRegistry([*first, *second])

    (problem,) = registry.problems
    assert problem.names == {"demo"}
    assert "plug-a 1.0, plug-b 2.0" in problem.message


def test_looking_up_a_scheme_registered_twice_raises_naming_both_distributions(
    make_distribution,
) -> None:
    first = make_distribution("plug-a", "1.0", {"ditto_backends": {"demo": _FACTORY}})
    second = make_distribution("plug-b", "2.0", {"ditto_backends": {"demo": _FACTORY}})
    registry = BackendRegistry([*first, *second])

    with pytest.raises(
        DittoBackendConflictError,
        match=r"'demo' is registered more than once, by plug-a 1.0, plug-b 2.0",
    ):
        registry["demo"]


def test_a_conflict_leaves_other_schemes_usable(make_distribution) -> None:
    first = make_distribution(
        "plug-a", "1.0", {"ditto_backends": {"demo": _FACTORY, "solo": _FACTORY}}
    )
    second = make_distribution("plug-b", "2.0", {"ditto_backends": {"demo": _FACTORY}})
    registry = BackendRegistry([*first, *second])

    assert registry["solo"] is dict_factory


def _registrations(*pairs: tuple[str, str]) -> list[Registration]:
    return [Registration(scheme, Distribution(dist, "1.0")) for scheme, dist in pairs]


def test_accepts_valid_schemes() -> None:
    registrations = _registrations(
        ("redis", "a"), ("postgresql", "b"), ("git+ssh", "c"), ("x-y.z2", "d")
    )

    assert find_scheme_problems(registrations) == []


@pytest.mark.parametrize("scheme", ["Redis", "2fa", "my_scheme", "has space", ""])
def test_rejects_a_scheme_no_uri_can_name(scheme: str) -> None:
    (problem,) = find_scheme_problems(_registrations((scheme, "plug")))

    assert problem.names == {scheme}
    assert "is not valid" in problem.message
    assert "plug 1.0" in problem.message


def test_rejects_a_scheme_ditto_resolves_itself() -> None:
    (problem,) = find_scheme_problems(_registrations(("file", "plug")))

    assert problem.names == {"file"}
    assert "never used" in problem.message


def test_problems_do_not_depend_on_discovery_order() -> None:
    pairs = [("b", "x"), ("b", "y"), ("a", "x"), ("a", "y"), ("Bad", "z")]

    forward = find_scheme_problems(_registrations(*pairs))
    backward = find_scheme_problems(_registrations(*reversed(pairs)))

    assert forward == backward


# ── Overrides ──────────────────────────────────────────────────────────────────


def test_an_override_takes_precedence_over_the_discovered_factory() -> None:
    ep = _ep("demo", load_return=dict_factory)
    registry = BackendRegistry([ep])

    registry.overrides["demo"] = other_factory

    assert registry["demo"] is other_factory
    assert list(registry) == ["demo"]
    ep.load.assert_not_called()


def test_an_override_resolves_a_conflict(make_distribution) -> None:
    first = make_distribution("plug-a", "1.0", {"ditto_backends": {"demo": _FACTORY}})
    second = make_distribution("plug-b", "2.0", {"ditto_backends": {"demo": _FACTORY}})
    registry = BackendRegistry([*first, *second])

    registry.overrides["demo"] = other_factory

    assert registry["demo"] is other_factory


def test_deleting_an_override_reveals_the_discovered_factory() -> None:
    registry = BackendRegistry([_ep("demo", load_return=dict_factory)])
    registry.overrides["demo"] = other_factory

    del registry.overrides["demo"]

    assert registry["demo"] is dict_factory


def test_overrides_contain_only_schemes_set_on_them() -> None:
    ep = _ep("demo", load_return=dict_factory)
    registry = BackendRegistry([ep])

    assert "demo" not in registry.overrides
    assert registry.overrides.pop("demo", None) is None
    with pytest.raises(KeyError):
        del registry.overrides["demo"]
    ep.load.assert_not_called()


def test_clearing_overrides_keeps_discovered_schemes() -> None:
    ep = _ep("demo", load_side_effect=ImportError("missing lib"))
    registry = BackendRegistry([ep])
    registry.overrides["demo"] = other_factory
    registry.overrides["local"] = other_factory

    registry.overrides.clear()

    assert len(registry.overrides) == 0
    assert list(registry) == ["demo"]
    ep.load.assert_not_called()


def test_schemes_set_only_as_overrides_follow_discovered_ones() -> None:
    registry = BackendRegistry([_ep("demo", load_return=dict_factory)])

    registry.overrides["extra"] = other_factory
    registry.overrides["demo"] = other_factory

    assert list(registry) == ["demo", "extra"]
    assert len(registry) == 2


def test_registry_is_read_only() -> None:
    registry = BackendRegistry([_ep("demo", load_return=dict_factory)])

    with pytest.raises(TypeError, match=r"BACKEND_REGISTRY.overrides\['demo'\]"):
        registry["demo"] = other_factory  # type: ignore[index]
    with pytest.raises(TypeError, match="overrides"):
        del registry["demo"]  # type: ignore[attr-defined]

    assert len(registry.overrides) == 0


def test_monkeypatch_setitem_adds_and_removes_a_scheme() -> None:
    registry = BackendRegistry([])

    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(registry.overrides, "demo", dict_factory)
        assert registry["demo"] is dict_factory

    assert "demo" not in registry


def test_monkeypatch_setitem_restores_the_discovered_factory() -> None:
    ep = _ep("demo", load_return=dict_factory)
    registry = BackendRegistry([ep])

    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(registry.overrides, "demo", other_factory)
        assert registry["demo"] is other_factory

    assert "demo" not in registry.overrides
    assert registry["demo"] is dict_factory


def test_monkeypatch_setitem_replaces_a_backend_that_fails_to_load() -> None:
    ep = _ep("demo", load_side_effect=ImportError("missing lib"))
    registry = BackendRegistry([ep])

    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(registry.overrides, "demo", other_factory)
        assert registry["demo"] is other_factory

    ep.load.assert_not_called()
    with pytest.raises(DittoBackendLoadError):
        registry["demo"]


def test_monkeypatch_setitem_replaces_a_conflicting_backend(make_distribution) -> None:
    first = make_distribution("plug-a", "1.0", {"ditto_backends": {"demo": _FACTORY}})
    second = make_distribution("plug-b", "2.0", {"ditto_backends": {"demo": _FACTORY}})
    registry = BackendRegistry([*first, *second])

    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(registry.overrides, "demo", other_factory)
        assert registry["demo"] is other_factory

    with pytest.raises(DittoBackendConflictError):
        registry["demo"]


def test_overriding_with_a_value_that_is_not_callable_is_rejected() -> None:
    registry = BackendRegistry([])

    with pytest.raises(TypeError, match="not callable"):
        registry.overrides["demo"] = object()  # type: ignore[assignment]


@pytest.mark.parametrize("scheme", ["Redis", "file"])
def test_overriding_a_scheme_no_target_can_reach_is_rejected(scheme: str) -> None:
    registry = BackendRegistry([])

    with pytest.raises(
        DittoBackendConflictError, match=r"from BACKEND_REGISTRY\.overrides"
    ):
        registry.overrides[scheme] = dict_factory

    assert scheme not in registry
