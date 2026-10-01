# ditto status

The inventory's one summary: total count, total size, a breakdown by recorder
type, and the oldest and newest snapshot — each named the way `ditto list` names
a snapshot. Where each snapshot lives is [`ditto stats`](stats.md).

## Usage

```
ditto status [PATH]
```

## Examples

```bash
# Show status for all snapshots
ditto status

# Show status for a specific directory
ditto status tests/ci/
```

## Output

A panel, laid out to fit the terminal:

- Total snapshot count and total size
- Breakdown by recorder type (count and size)
- The oldest and newest snapshot, each with its date, target and full identity

The oldest and newest are named by the test, key and recorder `ditto.lock`
records, falling back to the storage name for a snapshot the lock doesn't
record. The per-recorder counts appear here and not in `ditto stats`, so they
are only in one place.

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
