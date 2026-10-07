# Python API

The public Python API: the names each module lists in `__all__`. Everything
else in the `ditto` package is internal and can change without notice.

Most projects only need the `snapshot` fixture and the marks; see
[How Snapshots Work](../concepts/snapshots.md). The API matters when you
construct a `Snapshot` directly, write a recorder or a backend, or handle
ditto's errors.

| Module | Contents |
|--------|----------|
| [`ditto`](ditto.md) | `Snapshot`, `SnapshotMode`, the `record`, `json` and `yaml` marks, and `version` |
| [`ditto.recorders`](recorders.md) | The `Recorder` type and the recorder registry; see [Writing a Recorder](../guides/custom-recorders.md) |
| [`ditto.backends`](backends.md) | Backend helpers and the backend registry; see [Writing a Backend](../guides/custom-backends.md) |
| [`ditto.exceptions`](exceptions.md) | ditto's own exceptions, all subclasses of `DittoException`, and the `DittoWarning` category |

For settings, fixtures and command-line options, see
[Configuration](configuration.md); for the `ditto` command, the
[CLI reference](../cli/index.md).
