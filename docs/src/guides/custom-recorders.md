# Custom Recorders

Create your own recorder to support any serialisation format.

## Recorder Definition

A `Recorder` is a frozen dataclass with three fields:

```python
from pathlib import Path
from ditto.recorders import Recorder


def _save(data: MyType, filepath: Path) -> None:
    """Write data to filepath."""
    ...


def _load(filepath: Path) -> MyType:
    """Read and return data from filepath."""
    ...


my_recorder: Recorder[MyType] = Recorder(
    extension="myformat",
    save=_save,
    load=_load,
)
```

| Field | Type | Description |
|-------|------|-------------|
| `extension` | `str` | File extension appended to snapshot names |
| `save` | `Callable[[T, Path], None]` | Serialises a value to a file path |
| `load` | `Callable[[Path], T]` | Deserialises a value from a file path |

## Registration via Entry Points

Register your recorder in `pyproject.toml` under the `ditto_recorders` group:

```toml
[project.entry-points.ditto_recorders]
my_recorder = "my_package.recorders:my_recorder"
```

Once registered, it's available by name:

```python
import ditto

@ditto.record("my_recorder")
def test_something(snapshot):
    data = produce()
    assert data == snapshot(data, key="output")
```

## Registering Custom Marks

For a cleaner API (e.g., `@ditto.myplugin.myformat`), register marks via the
`ditto_marks` entry point group:

```toml
[project.entry-points.ditto_marks]
myplugin = "my_package.marks:myplugin"
```

The mark object should be a namespace that provides mark attributes. See the
`pytest-ditto-pandas` source for a complete example.

## Example: MessagePack Recorder

```python
from pathlib import Path
import msgpack
from ditto.recorders import Recorder


def _save_msgpack(data: dict, filepath: Path) -> None:
    filepath.write_bytes(msgpack.packb(data))


def _load_msgpack(filepath: Path) -> dict:
    return msgpack.unpackb(filepath.read_bytes())


msgpack_recorder: Recorder[dict] = Recorder(
    extension="msgpack",
    save=_save_msgpack,
    load=_load_msgpack,
)
```

Register it:

```toml
[project.entry-points.ditto_recorders]
msgpack = "my_package:msgpack_recorder"
```

Use it:

```python
@ditto.record("msgpack")
def test_with_msgpack(snapshot):
    data = {"key": "value", "numbers": [1, 2, 3]}
    assert data == snapshot(data, key="packed")
```

## Extension Naming

The `extension` field is the canonical identifier appended to snapshot keys.
It may contain dots for namespaced recorders:

- Built-in: `pkl`, `yaml`, `json`
- Plugin: `pandas.parquet`, `pandas.csv`, `pyarrow.feather`

The extension does not need to match the mark alias or registry key.
