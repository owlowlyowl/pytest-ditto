# ditto status

Shows aggregate statistics: total count, total size, breakdown by recorder
type, and oldest/newest snapshot dates.

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

## Screenshot

![ditto status](../img/ditto-status.png)

## Output

Displays:

- Total snapshot count
- Total size on disk
- Breakdown by recorder type (count and size)
- Oldest and newest snapshot dates
