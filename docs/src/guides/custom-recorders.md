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
    identifier="myformat",
    save=_save,
    load=_load,
)
```

| Field | Type | Description |
|-------|------|-------------|
| `identifier` | `str` | Persisted identifier appended to snapshot names and recorded in `ditto.lock` |
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

## Marks

Every registered recorder gets a mark, derived from its entry-point name. A bare
name `myformat` is exposed as `@ditto.myformat`. A dotted name
`myplugin.myformat` is exposed as `@ditto.myplugin.myformat`. Both are
shorthands for `@ditto.record("<name>")`:

```toml
[project.entry-points.ditto_recorders]
"myplugin.myformat" = "my_package.recorders:myformat"
```

```python
@ditto.myplugin.myformat
def test_something(snapshot):
    ...
```

Resolving a mark reads only the installed entry-point names; the recorder is
imported the first time a test uses it. A misspelled format, such as
`@ditto.myplugin.myfromat`, fails at collection with the formats that are
available under `myplugin`.

## Naming Rules

A recorder's entry-point name is its user-facing name. It must be `<format>` or
`<namespace>.<format>`, where each segment is a lowercase letter followed by
lowercase letters, digits or underscores. Name a plugin's recorders
`<namespace>.<format>`, with the plugin's name as the namespace.

These registrations conflict:

- the same name registered by more than one distribution
- two recorders with the same `identifier`, which would read and write each
  other's snapshot files
- a bare name that is also a namespace, such as `tabular` alongside
  `tabular.csv`, which makes `@ditto.tabular` ambiguous
- a name that shadows an attribute of `ditto`, such as `record` or `version`

ditto never picks one of the conflicting registrations. Each pytest run emits a
`DittoWarning` for every conflict, a test that uses an affected recorder fails
with `DittoRecorderConflictError` naming the distributions involved, and
`ditto doctor` fails. Other recorders keep working. Identifier conflicts are
found when both recorders load; `ditto doctor` loads every recorder, so it
finds them all.

Plugins written for the 1.x contract, which registered marks under the removed
`ditto_marks` group, are reported the same way, with the version to install.

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
    identifier="msgpack",
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

## Identifier Naming

The `identifier` field is appended to snapshot keys and recorded in `ditto.lock`.
It may contain dots for namespaced recorders:

- Built-in: `json`, `yaml`
- Plugin: `pandas.parquet`, `pandas.csv`, `pyarrow.feather`

The identifier does not need to match the mark alias or registry key.
