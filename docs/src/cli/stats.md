# ditto stats

Shows where the snapshots live: a row per target — each `.ditto/` directory or
remote URI — with the snapshot count and total size for it, and a total row.
Per-recorder counts are [`ditto status`](status.md)'s.

## Usage

```
ditto stats [PATH]
```

## Examples

```bash
# Show stats for all targets
ditto stats

# Show stats for the targets under a path
ditto stats tests/ci/
```

## Output

A table with a total footer:

| Column | Description |
|--------|-------------|
| Directory | The target: a path relative to the current directory, or a remote URI whole |
| Snapshots | Number of snapshots in that target |
| Size | Total size of snapshots in that target |

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
