import types

from ditto.exceptions import DittoWarning
from ditto.plugin import _warn_if_lockfile_ignored


def test_ditto_warning_is_a_user_warning():
    """DittoWarning subclasses UserWarning so existing filters still apply."""
    assert issubclass(DittoWarning, UserWarning)


def test_gitignore_guard_warns_with_ditto_category(tmp_path, recwarn):
    """The .gitignore guard emits its advisory under the DittoWarning category."""
    (tmp_path / ".gitignore").write_text("ditto.lock\n")

    _warn_if_lockfile_ignored(types.SimpleNamespace(rootpath=tmp_path))

    assert any(issubclass(w.category, DittoWarning) for w in recwarn.list)
