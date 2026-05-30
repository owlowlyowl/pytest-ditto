# ditto update

Regenerates snapshots by running pytest with `--ditto-update`. All snapshot
files touched by the run will be overwritten with current values.

## Usage

```
ditto update [PATH] [PYTEST_ARGS...]
```

## Examples

```bash
# Update all snapshots
ditto update

# Update snapshots in a specific directory
ditto update tests/ci/

# Update specific tests
ditto update tests/ci/ -k test_foo
```

## Screenshot

![ditto update](../img/ditto-update.png)

## Behaviour

- Runs pytest with `--ditto-update` flag
- Every snapshot encountered during the run is re-recorded from current output
- Existing snapshot files are overwritten
- New snapshots are created as normal

!!! tip
    After updating, review the diff in version control to verify the changes
    are intentional.
