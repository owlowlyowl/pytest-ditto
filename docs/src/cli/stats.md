# ditto stats

Shows where snapshots are stored: one row per target, a local `.ditto/`
directory or a remote URI, with its snapshot count and size. Complements
`ditto status`, which totals snapshots by recorder.

## Usage

```
ditto stats [PATH]
```

## Examples

```bash
# Show stats for every target
ditto stats

# Show stats for a specific path
ditto stats tests/ci/
```

## Output

Displays a table with columns:

| Column | Description |
|--------|-------------|
| Directory | The target: a `.ditto/` directory, or a remote URI |
| Snapshots | Number of snapshots in the target |
| Size | Their total size (`—` when unknown, for remote snapshots read from the lock) |
| Recorders | How many snapshots each recorder wrote, e.g. `json×2` |

A **TOTAL** row sums the snapshots and sizes across targets.

## Data source

By default this command is **credential-free**: local snapshots are read from the
filesystem (real size and modified date, including on-disk orphans) and remote
snapshots are read from `ditto.lock` (shown with `—` for size and modified, since
physical metadata needs a live connection). No test modules are imported and no
credentials are needed.

Pass `--live` to read the live backends instead, via an internal
`pytest --setup-only` pass — authoritative physical state for every target, at the
cost of importing your tests and needing their credentials.

Totals cover only snapshots with a known size; remote (lock-derived) snapshots are
reported separately as "size unknown (use --live)".

See [The Lock File](../guides/lock-file.md#declared-vs-physical-state-and-the-inventory-trade-off).
