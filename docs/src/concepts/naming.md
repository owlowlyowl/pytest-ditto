# Snapshot Names

Every snapshot is stored under a name built from the test that owns it. You
rarely need to read these names: `ditto.lock` records each snapshot's exact test
and key, and [`ditto list`](../cli/list.md) shows them. This page explains the
names for when you do, such as when reviewing a diff or writing a
[backend](../guides/custom-backends.md).

## The parts of a name

A name has five parts: the test module, the test, the snapshot key, a short
hash, and the recorder. With the project root as pytest's rootdir, a test
`test_create` in `tests/api/test_users.py` that calls
`snapshot(value, key="response")` with the `json` recorder is stored as:

```
tests/api/.ditto/tests.api.test_users.test_create@response~90e755f5c20755bd.json
                 └────────┬─────────┘ └────┬────┘ └──┬───┘ └──────┬───────┘ └┬─┘
                     test module         test       key         hash     recorder
```

| Part | What it is |
|---|---|
| test module | The test file's path relative to pytest's rootdir, without its extension. |
| test | The test's name within the module, from its pytest node ID. A test in a class includes the class (`TestUsers.test_create`), and a parametrized test includes its ID (`test_create[admin]`). |
| key | The `key` passed to `snapshot()`. |
| hash | The first 16 hex characters of a SHA-256 of the test's exact node ID, the key and the recorder. |
| recorder | The name of the [recorder](../guides/recorders.md) that wrote the snapshot, such as `json` or `pandas.parquet`. |

## Local files and remote storage

A [`file://` target](../guides/backends.md#local-files-file), including the
default `.ditto` directory, stores each snapshot as one file. The module path's
slashes become dots, so every file sits directly in the directory, as above.

Any other target stores one object per snapshot under the URI's path, and the
module path keeps its slashes. The same test, with
`target="s3://my-bucket/snapshots/"`, is stored as:

```
s3://my-bucket/snapshots/tests/api/test_users/test_create@response~90e755f5c20755bd.json
                         └────────┬─────────┘ └────┬────┘ └──┬───┘ └──────┬───────┘ └┬─┘
                             test module         test       key         hash     recorder
```

## Safe characters and length

The test and key are there to be read, not decoded, so they're made safe for
every file system: characters other than ASCII letters, digits and
`. _ - [ ] = , +` become `_`. The test is shortened to 80 characters and the
key to 40.

A local file name must also fit in 255 bytes. If the module path is long, the
test and key are shortened further to make room; a module path too long to
leave room for them is an error. A remote name isn't a file name, so it has no
such limit.

## Why the hash

Replacing characters and ignoring case can give two snapshots the same
readable part. The hash, taken from the exact node ID rather than the readable
part, keeps them apart:

| Test | File |
|---|---|
| `test_at[12:00]` | `tests.test_api.test_at[12_00]@body~6617c5399a6ba420.json` |
| `test_at[12_00]` | `tests.test_api.test_at[12_00]@body~105d78e147145d58.json` |
| `test_at[A]` | `tests.test_api.test_at[A]@body~46cccc8d4a59c1ef.json` |
| `test_at[a]` | `tests.test_api.test_at[a]@body~a99f8460327efdf4.json` |

`[A]` and `[a]` would otherwise be the same file name on Windows and macOS,
whose file systems ignore case.

Because the name depends on the node ID, renaming or moving a test, changing a
parametrize ID, changing a key, or switching recorder all give the snapshot a
new name. The old snapshot stays where it was until you
[prune it](../guides/maintaining.md#remove-snapshots-you-no-longer-need).

## Writes and temporary files

A local snapshot is written to a temporary file next to it, then renamed into
place, so a write that fails partway through (a full disk, an interrupted run)
leaves the previous snapshot intact. An overwritten snapshot keeps its
permissions. A process killed mid-write can leave the temporary file behind:
`.ditto-tmp-`, then 32 hex characters, then `.tmp`. ditto ignores it, and it's
safe to delete.
