# ditto list

Lists all snapshot files found under a path in a table showing test name,
key, recorder, file size, and last-modified date.

## Usage

```
ditto list [--flat] [--live] [PATH]
```

## Examples

```bash
# List all snapshots
ditto list

# List snapshots in a specific directory
ditto list tests/ci/

# Show full pytest node IDs on individual rows
ditto list --flat
```

## Screenshot

![ditto list](../img/ditto-list.svg)

## Output

Groups snapshots by **storage target**, then by **test file**, with tree branches
for the tests beneath each file. Shared file paths appear once; keys, recorders,
and sizes stay aligned with their snapshot rows. Local targets are relative to
the current directory where possible, and remote targets retain their URI.

Exact test names and keys come from `ditto.lock`. Without a matching entry,
the stored filename's labels remain intact; when a lock exists, unmatched
snapshots are marked `not in lock`. Labels are never guessed into file paths.
Use `--flat` to show complete node IDs on each row.

Long names wrap instead of being truncated. Below 100 columns, size and modified
date share a **Details** column; below 60 columns it also includes the key and
recorder. The footer reports the number of snapshots and targets.

At wider terminal widths the columns are:

| Column | Description |
|--------|-------------|
| Target / test | Storage target, test file, and test name (full node ID with `--flat`) |
| Key | Snapshot key |
| Recorder | Format used (json, yaml, external formats, etc.) |
| Size | File size |
| Modified | Last-modified date |

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
