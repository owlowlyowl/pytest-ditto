# unittest Support

`DittoTestCase` provides the `snapshot` fixture as a `cached_property` for use
with `unittest.TestCase`.

## Usage

```python
import unittest
from ditto import DittoTestCase


def fn(x: int) -> int:
    return x + 1


class TestFn(DittoTestCase):
    def test_fn(self):
        result = fn(1)
        assert result == self.snapshot(result, key="fn")
```

## How It Works

`DittoTestCase` inherits from `unittest.TestCase` and adds a `snapshot`
cached property. Since unittest creates a fresh instance per test method,
the snapshot is naturally scoped to one test.

Snapshot files are placed in a `.ditto/` directory adjacent to the test file,
using the fully-qualified test method name as the group name (e.g.,
`TestFn.test_fn`).

## Recorder Selection

`DittoTestCase` uses the default pickle recorder. To use a different recorder
with unittest-style tests, use the pytest test runner with marks instead:

```python
import pytest
import ditto


@ditto.json
class TestWithJson:
    def test_something(self, snapshot):
        data = {"key": "value"}
        assert data == snapshot(data, key="data")
```

## Limitations

- `DittoTestCase` always uses the local `file://` backend (`.ditto/` directory)
- Remote backends and profiles require the pytest fixture-based approach
- Recorder selection via marks is not supported on `DittoTestCase` methods
