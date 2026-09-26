# pytest-ditto-pickle

Extension plugin for [`pytest-ditto`](https://github.com/owlowlyowl/pytest-ditto) that records snapshots with Python's `pickle`.

> [!WARNING]
> Loading pickle data can execute arbitrary code. Only load snapshots you
> trust, and never load a `.pkl` snapshot from an untrusted source, such as a
> pull request from someone you don't know. Review changes to `.pkl` files as
> carefully as changes to code.

pytest-ditto records snapshots as strict JSON by default. Use pickle only when
a value can't be represented in JSON, or YAML, or one of the other recorders,
and you accept the risk above.

## Installation
```bash
pip install pytest-ditto-pickle
```

pytest-ditto has no `pickle` extra: install this package by name, deliberately.

## Usage

Select the recorder explicitly on each test, with `@ditto.pickle` or its
long form, `@ditto.record("pickle")`:

```python
import datetime

import ditto


@ditto.pickle
def test_schedule(snapshot):
    schedule = {"days": {"mon", "wed"}, "start": datetime.time(9, 30)}
    assert snapshot(schedule, key="schedule") == schedule
```

## Snapshots from pytest-ditto 1.x

pytest-ditto 1.x used pickle by default and saved snapshots with the `.pkl`
extension. This recorder keeps that extension and file format, so a 1.x
`.pkl` file loads unchanged.

pytest-ditto 2.0 names snapshot files differently, though, so 2.0 won't find a
1.x file where 1.x left it. See the pytest-ditto upgrade guide for the new
names.
