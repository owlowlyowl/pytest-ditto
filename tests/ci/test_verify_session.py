import types

from ditto.exceptions import DittoWarning
from ditto.plugin import _warn_if_lockfile_ignored
from ditto.snapshot import _SessionTracker


def test_ditto_warning_is_a_user_warning():
    """DittoWarning subclasses UserWarning so existing filters still apply."""
    assert issubclass(DittoWarning, UserWarning)


def test_gitignore_guard_warns_with_ditto_category(tmp_path, recwarn):
    """The .gitignore guard emits its advisory under the DittoWarning category."""
    (tmp_path / ".gitignore").write_text("ditto.lock\n")

    _warn_if_lockfile_ignored(types.SimpleNamespace(rootpath=tmp_path))

    assert any(issubclass(w.category, DittoWarning) for w in recwarn.list)


def test_tracker_registers_target_backend():
    """A target id maps to its (scheme, backend) for later enumeration."""
    tracker = _SessionTracker()
    backend = object()

    tracker.register_target_backend("tests/.ditto", "file", backend)

    assert tracker.target_backends["tests/.ditto"] == ("file", backend)


def test_tracker_reset_clears_target_backends():
    """Reset drops registered target backends."""
    tracker = _SessionTracker()
    tracker.register_target_backend("tests/.ditto", "file", object())

    tracker.reset()

    assert tracker.target_backends == {}
