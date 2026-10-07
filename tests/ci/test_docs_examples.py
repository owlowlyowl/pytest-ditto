"""The documentation's runnable examples behave as the docs say.

An example is marked runnable by an HTML comment on the line before its code
block, which the rendered page doesn't show:

    <!-- test: passes -->
    ```python
    def test_...(snapshot): ...
    ```

`passes` examples must pass when first recorded and again when compared with
what they recorded. `fails` examples illustrate a mistake and must fail.
"""

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS = [ROOT / "README.md", *sorted((ROOT / "docs" / "src").rglob("*.md"))]

_EXAMPLE = re.compile(
    r"^<!-- test: (?P<outcome>passes|fails) -->\n```python\n(?P<code>.*?)^```$",
    re.MULTILINE | re.DOTALL,
)


def _examples(outcome: str) -> list:
    """Return a pytest param per example marked `outcome`, with its location."""
    params = []
    for document in DOCUMENTS:
        text = document.read_text(encoding="utf-8")
        for match in _EXAMPLE.finditer(text):
            if match["outcome"] != outcome:
                continue
            line = text.count("\n", 0, match.start()) + 1
            location = f"{document.relative_to(ROOT).as_posix()}:{line}"
            params.append(pytest.param(match["code"], id=location))
    return params


PASSING = _examples("passes")
FAILING = _examples("fails")


def test_finds_the_marked_examples_when_collecting() -> None:
    """The marker pattern matches the docs, so the examples below aren't skipped."""
    assert PASSING
    assert FAILING


@pytest.mark.parametrize("code", PASSING)
def test_example_passes_when_recorded_and_compared(pytester, code) -> None:
    """A passing example records its snapshots, then matches them on a rerun."""
    pytester.makepyfile(test_example=code)

    recorded = pytester.runpytest()
    compared = pytester.runpytest()

    assert recorded.ret == pytest.ExitCode.OK
    assert compared.ret == pytest.ExitCode.OK


@pytest.mark.parametrize("code", FAILING)
def test_example_fails_when_run(pytester, code) -> None:
    """An example of a mistake fails, as the docs say it does."""
    pytester.makepyfile(test_example=code)

    result = pytester.runpytest()

    result.assert_outcomes(failed=1)
