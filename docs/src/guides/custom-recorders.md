# Custom Recorders

Create your own recorder to support any serialisation format.

## Recorder Definition

A `Recorder` is a frozen dataclass with two fields:

```python
from ditto.recorders import Recorder


def _dumps(data: MyType) -> bytes:
    """Serialise data to bytes."""
    ...


def _loads(raw: bytes) -> MyType:
    """Deserialise bytes produced by _dumps."""
    ...


my_recorder: Recorder[MyType] = Recorder(dumps=_dumps, loads=_loads)
```

| Field | Type | Description |
|-------|------|-------------|
| `dumps` | `Callable[[T], bytes]` | Serialises a value to bytes |
| `loads` | `Callable[[bytes], T]` | Deserialises bytes back to a value |

When recording or updating a snapshot, or verifying a missing snapshot,
`snapshot()` returns `loads(dumps(value))`, so a test sees what later runs will
read back. In RECORD or VERIFY mode, an existing snapshot returns
`loads(stored_bytes)` without serialising the supplied value.
If `loads` can't read the bytes `dumps` produced, nothing is written. `dumps`
must not modify the value it is given, because the test compares that value
with the one `snapshot()` returns.

The bytes are the snapshot file's contents, stored as they are: a text format
stays readable and diffable. Write text with `"\n"` line endings rather than the
platform's, so a snapshot's bytes are the same on every machine.

Snapshots are handled whole: the value and its serialised bytes must fit in
memory together.

### Libraries that only read and write files

If a library can't serialise to bytes, wrap its file functions with
`recorder_from_files`:

```python
from pathlib import Path
from ditto.recorders import recorder_from_files


def _save(data: MyType, path: Path) -> None: ...


def _load(path: Path) -> MyType: ...


my_recorder = recorder_from_files(save=_save, load=_load, suffix=".myformat")
```

Each call writes or reads a temporary file named `snapshot<suffix>` in its own
temporary directory, which is removed afterwards even if the call fails. The
suffix only names that temporary file; the snapshot's filename still comes
from the recorder's registered name. Only single-file formats work, and a value
returned by `_load` must not depend on the file after `_load` returns, so lazy
or memory-mapped readers are unsuitable. Prefer an in-memory API where the
library has one: it avoids the file I/O.

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

A recorder's name is also its persisted identifier: it ends the recorder's
snapshot filenames and is recorded in `ditto.lock`. Renaming a recorder
therefore renames its snapshot files.

These registrations conflict:

- the same name registered by more than one distribution, which would read and
  write each other's snapshot files
- a bare name that is also a namespace, such as `tabular` alongside
  `tabular.csv`, which makes `@ditto.tabular` ambiguous
- a name that shadows an attribute of `ditto`, such as `record` or `version`

Conflicts are found from the installed entry-point metadata, without importing
any recorder, so a conflicting plugin is found even if no test uses it. ditto
never picks one of the conflicting registrations: pytest stops before
collecting any tests, listing every conflict and the distributions involved,
and `ditto doctor` fails.

Plugins written for the 1.x contract, which registered marks under the removed
`ditto_marks` group, are reported the same way, with the version to install.

## Registering in `conftest.py`

A project can register a recorder without packaging it:

```python
# conftest.py
from ditto import recorders

recorders.register("myproject.myformat", my_recorder)
```

`register` follows the same naming rules and raises
`DittoRecorderConflictError` if the name conflicts with one already
registered. It never replaces an installed recorder.

## Example: MessagePack Recorder

```python
import msgpack
from ditto.recorders import Recorder


msgpack_recorder: Recorder[dict] = Recorder(
    dumps=msgpack.packb, loads=msgpack.unpackb
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

Its snapshots are saved as `<key>.msgpack`.
