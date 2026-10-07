# pickle

`pytest-ditto-pickle` records snapshots with Python's `pickle`.

!!! danger "Loading pickle data can execute arbitrary code"
    Only load snapshots you trust, and never load a `.pickle` snapshot from an
    untrusted source, such as a pull request from someone you don't know.
    Review changes to `.pickle` files as carefully as changes to code.

pytest-ditto records snapshots as strict JSON by default. Use pickle only when
a value can't be represented in JSON, YAML or one of the other recorders, and
you accept the risk above.

```bash
pip install pytest-ditto pytest-ditto-pickle
```

pytest-ditto has no `pickle` extra: install this package by name, deliberately.

| Mark | Recorder | Stores |
|------|----------|--------|
| `@ditto.pickle` | `pickle` | Python's `pickle` format |

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

A value is compared with `==`, so its type needs a meaningful `__eq__`.

## Snapshots from pytest-ditto 1.x

pytest-ditto 1.x used pickle by default and saved snapshots with the `.pkl`
extension. This recorder writes the same pickle format, but pytest-ditto 2.0
names snapshot files differently, so it won't find a 1.x file. Re-record each
snapshot with this recorder, review the result, and delete the old `.pkl`
files; see [Upgrading to 2.0](../upgrading.md).
