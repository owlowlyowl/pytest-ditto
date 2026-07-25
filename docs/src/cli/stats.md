# ditto stats

Shows a per-directory snapshot usage breakdown (file count and total size per
`.ditto/` directory). Complements `ditto status`, which shows session-level
aggregates.

## Usage

```
ditto stats [PATH]
```

## Examples

```bash
# Show stats for all directories
ditto stats

# Show stats for a specific path
ditto stats tests/ci/
```

## Output

Displays a table with columns:

| Column | Description |
|--------|-------------|
| Directory | Path to the `.ditto/` directory |
| Files | Number of snapshot files |
| Size | Total size of snapshots in that directory |

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
