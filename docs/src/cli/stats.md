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
