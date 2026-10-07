# pytest-ditto-pickle

A [pytest-ditto](https://github.com/owlowlyowl/pytest-ditto) plugin that records snapshots with Python's `pickle`.

**[Documentation](https://owlowlyowl.github.io/pytest-ditto/plugins/pickle/)**

> [!WARNING]
> Loading pickle data can execute arbitrary code. Only load snapshots you
> trust, and never load a `.pickle` snapshot from an untrusted source, such as a
> pull request from someone you don't know. Review changes to `.pickle` files as
> carefully as changes to code.

pytest-ditto records snapshots as strict JSON by default. Use pickle only when
a value can't be represented in JSON, YAML or one of the other recorders, and
you accept the risk above.

## Installation

```bash
pip install pytest-ditto pytest-ditto-pickle
```

pytest-ditto has no `pickle` extra: install this package by name, deliberately.

## Usage

Select the recorder explicitly on each test, with `@ditto.pickle` or its long
form, `@ditto.record("pickle")`:

```python
import datetime

import ditto


@ditto.pickle
def test_schedule(snapshot):
    schedule = {"days": {"mon", "wed"}, "start": datetime.time(9, 30)}
    assert snapshot(schedule, key="schedule") == schedule
```

pytest-ditto 2.0 doesn't find snapshots recorded by 1.x, including `.pkl`
files: re-record them with this recorder. See the documentation.
