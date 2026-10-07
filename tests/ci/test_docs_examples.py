"""The documentation's runnable examples behave as the docs say.

An example is marked runnable by an HTML comment on the line directly before
its code block, which the rendered page doesn't show:

    <!-- test: passes -->
    ```python
    def test_...(snapshot): ...
    ```

A `passes` example must pass when it records its snapshots, and again under
`--ditto-verify`. A failing example illustrates a mistake and names the error
text it must produce: `<!-- test: fails DuplicateSnapshotKeyError -->`.
"""

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS = [ROOT / "README.md", *sorted((ROOT / "docs" / "src").rglob("*.md"))]

# Anything that looks like a marker, so a mistyped one is reported, not ignored.
_MARKER_LIKE = re.compile(r"^.*<!--\s*tests?\b.*$", re.MULTILINE)
_EXAMPLE = re.compile(
    r"^<!-- test: (?:(?P<passes>passes)|fails (?P<error>\S.*?)) -->\n"
    r"```python\n(?P<code>.*?)^```$",
    re.MULTILINE | re.DOTALL,
)


def _location(document: Path, text: str, offset: int) -> str:
    line = text.count("\n", 0, offset) + 1
    return f"{document.relative_to(ROOT).as_posix()}:{line}"


def _scan() -> tuple[list, list, list[str]]:
    """Return (passing params, failing params, locations of malformed markers)."""
    passing, failing, malformed = [], [], []
    for document in DOCUMENTS:
        text = document.read_text(encoding="utf-8")
        examples = {m.start(): m for m in _EXAMPLE.finditer(text)}
        for marker in _MARKER_LIKE.finditer(text):
            location = _location(document, text, marker.start())
            example = examples.get(marker.start())
            if example is None:
                malformed.append(location)
            elif example["passes"]:
                passing.append(pytest.param(example["code"], id=location))
            else:
                failing.append(
                    pytest.param(example["code"], example["error"], id=location)
                )
    return passing, failing, malformed


PASSING, FAILING, MALFORMED = _scan()


def test_every_example_marker_is_followed_by_a_python_block() -> None:
    """No marker is mistyped or separated from its code block, which would skip it."""
    assert MALFORMED == []


def test_finds_the_marked_examples_when_collecting() -> None:
    """The docs have marked examples of each kind, so neither test is empty."""
    assert PASSING
    assert FAILING


@pytest.mark.parametrize("code", PASSING)
def test_example_passes_when_recorded_and_verified(pytester, code) -> None:
    """A passing example records its snapshots, then passes `--ditto-verify`."""
    pytester.makepyfile(test_example=code)

    recorded = pytester.runpytest()
    verified = pytester.runpytest("--ditto-verify")

    assert recorded.ret == pytest.ExitCode.OK
    assert verified.ret == pytest.ExitCode.OK


@pytest.mark.parametrize(("code", "error"), FAILING)
def test_example_fails_with_the_error_it_names(pytester, code, error) -> None:
    """An example of a mistake fails with the error its marker names."""
    pytester.makepyfile(test_example=code)

    result = pytester.runpytest()

    result.assert_outcomes(failed=1)
    assert error in result.stdout.str()
