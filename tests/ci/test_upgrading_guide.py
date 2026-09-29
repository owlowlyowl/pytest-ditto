"""The upgrading guide's snapshot rename script, run as the guide shows it."""

import re
import sys
from pathlib import Path

import pytest

GUIDE = Path(__file__).parents[2] / "docs" / "src" / "guides" / "upgrading.md"

# The old names use characters Windows file names can't hold, so the files the
# script renames can only exist elsewhere.
pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="the names being migrated can't exist on Windows"
)


def _rename_script() -> str:
    """The Python block following the guide's rename instructions."""
    text = GUIDE.read_text(encoding="utf-8")
    after = text[text.index("To keep the baselines of snapshots") :]
    match = re.search(r"```python\n(.*?)```", after, re.DOTALL)
    assert match is not None
    return match.group(1)


# Old name (relative to .ditto/) -> encoded name, for snapshots whose contents
# name the test that owns them. `[a:b]`'s new name is `[a%3Ab]`'s old one.
OLD_TO_NEW = {
    "m.test_a[a:b]@k.json": "m.test_a[a%3Ab]@k.json",
    "m.test_a[a%3Ab]@k.json": "m.test_a[a%253Ab]@k.json",
    "m.test_a[x/y]@k.json": "m.test_a[x%2Fy]@k.json",
    "m.test_a[plain]@k.json": "m.test_a[plain]@k.json",
}


@pytest.mark.parametrize("reverse", [False, True], ids=["sorted", "reversed"])
def test_rename_script_keeps_every_baseline(tmp_path, monkeypatch, reverse):
    """Every snapshot ends up under its encoded name with its own contents,
    whichever order the files are visited in."""
    ditto_dir = tmp_path / "tests" / ".ditto"
    for old in OLD_TO_NEW:
        path = ditto_dir / old
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(old)
    rglob = Path.rglob

    def ordered_rglob(self, pattern):
        return sorted(rglob(self, pattern), reverse=reverse)

    monkeypatch.setattr(Path, "rglob", ordered_rglob)
    monkeypatch.chdir(tmp_path)

    exec(_rename_script(), {})

    renamed = {
        p.relative_to(ditto_dir).as_posix(): p.read_text()
        for p in ditto_dir.rglob("*")
        if p.is_file()
    }
    assert renamed == {new: old for old, new in OLD_TO_NEW.items()}


def test_rename_script_refuses_to_overwrite_a_file_it_is_not_moving(
    tmp_path, monkeypatch
):
    """If an encoded name is already taken by a file that stays put, nothing moves."""
    ditto_dir = tmp_path / ".ditto"
    ditto_dir.mkdir()
    (ditto_dir / "m.test_a[a:b]@k.json").write_text("colon")
    # A directory can't be renamed by the script (it only moves files), so it
    # holds the encoded name without being moved itself.
    (ditto_dir / "m.test_a[a%3Ab]@k.json").mkdir()
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileExistsError, match="not renaming anything"):
        exec(_rename_script(), {})

    assert (ditto_dir / "m.test_a[a:b]@k.json").read_text() == "colon"
