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
