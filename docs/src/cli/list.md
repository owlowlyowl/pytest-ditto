# ditto list

Lists every snapshot found under a path, grouped by target and test file, so
the part that tells two snapshots apart — the test and its key — keeps the
width instead of a repeated path.

## Usage

```
ditto list [OPTIONS] [PATH]
```

| Option | Description |
|--------|-------------|
| `--live` | Read the live backends instead of the lock (see [Data source](#data-source)) |
| `--flat` | JSON Lines: one complete snapshot record per line, for `grep` and scripts |

## Examples

```bash
# List all snapshots
ditto list

# List snapshots owned by tests under a directory
ditto list tests/ci/

# One JSON object per snapshot, with the target and full node id
ditto list --flat
```

## Output

A table, laid out to fit the terminal:

| Column | Description |
|--------|-------------|
| Target / test | The target as a path relative to the current directory (a remote URI is shown whole), then the test file, then the test name |
| Key | Snapshot key, exactly as `ditto.lock` records it |
| Recorder | Format used (json, yaml, external formats, etc.) |
| Size | File size, or `—` when the inventory has no size for it |
| Modified | Last-modified date, or `—` |

A snapshot is named by the test that owns it, its key, and its recorder —
the same three facts everywhere ditto names a snapshot. The file heading is
printed once for all the snapshots in it, and a name `ditto.lock` doesn't
record (an orphan, or a snapshot recorded since the last `ditto lock`) is
listed after the files and marked `not in lock`.

The table adapts to the terminal width: below 60 columns a snapshot's key and
recorder move under its name, and below 80 the size and date share a cell.
Nothing is truncated — a long name wraps in the middle, so the part that tells
two rows apart stays visible.

A footnote gives the totals, for example `4 snapshots · 2 targets`.

## Script output

`ditto list --flat` writes JSON Lines to stdout, without headings, totals,
colour or wrapping. Each line is one self-contained snapshot record, regardless
of terminal width. Notes and errors go to stderr. An incomplete inventory exits
non-zero, even if some snapshot records were printed.

```bash
ditto list --flat > snapshots.jsonl
ditto list --flat | grep -F 'tests/test_a.py::test_numbers[1]'
```

Each record contains:

| Field | Value |
|-------|-------|
| `target` | Absolute resolved local path, or complete remote URI |
| `nodeid`, `key` | Exact lock identity, or `null` when unknown |
| `recorder` | Locked recorder name, falling back to the storage suffix, or `null` |
| `storage_key` | Complete backend key, including its hash |
| `size_bytes` | Size in bytes, or `null` when unknown |
| `modified` | POSIX timestamp, or `null` when unknown |
| `in_lock` | `true` if recorded, `false` if absent from a readable lock, or `null` if no readable lock is available |

JSON escaping preserves tabs, newlines, quotes and other special characters
without splitting a record across lines. For unknown identities, use `target`
and `storage_key`; the shortened labels in a storage name cannot recover the
original node ID or key.

## Data source

By default this command is **credential-free**: local snapshots are read from the
filesystem (real size and modified date, including on-disk orphans) and remote
snapshots are read from `ditto.lock` (shown with `—` for size and modified, since
physical metadata needs a live connection). No test modules are imported and no
credentials are needed.

Pass `--live` to read the live backends instead, via an internal
`pytest --setup-only` pass — authoritative physical state for every target, at the
cost of importing your tests and needing their credentials.

See [The Lock File](../guides/lock-file.md#declared-vs-physical-state-and-the-inventory-trade-off).
