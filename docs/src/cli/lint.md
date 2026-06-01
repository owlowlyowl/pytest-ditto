# ditto lint

Checks snapshot files for naming issues, unknown recorder formats, and empty
files. Exits non-zero if any issues are found.

## Usage

```
ditto lint [PATH]
```

## Examples

```bash
# Lint all snapshots
ditto lint

# Lint a specific directory
ditto lint tests/ci/
```

## Checks

| Check | Description |
|-------|-------------|
| Naming | Validates snapshot filenames match expected format |
| Format | Detects unknown recorder extensions |
| Empty | Flags zero-byte snapshot files |

## Exit Codes

- `0` — No issues found
- `1` — One or more issues detected

## Data source

By default this command is **credential-free**: local snapshots are read from the
filesystem (real size and modified date, including on-disk orphans) and remote
snapshots are read from `ditto.lock` (shown with `—` for size and modified, since
physical metadata needs a live connection). No test modules are imported and no
credentials are needed.

Pass `--live` to read the live backends instead, via an internal
`pytest --setup-only` pass — authoritative physical state for every target, at the
cost of importing your tests and needing their credentials.

The empty-file check is skipped for snapshots whose size is unknown without
`--live`.

See [The Lock File](../guides/lock-file.md#declared-vs-physical-state-and-the-inventory-trade-off).
