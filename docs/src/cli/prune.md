# ditto prune

Removes stale snapshots by running pytest with `--ditto-prune`. Snapshot files
not accessed during the run are deleted.

## Usage

```
ditto prune [PATH] [PYTEST_ARGS...]
```

## Examples

```bash
# Prune all stale snapshots
ditto prune

# Prune in a specific directory
ditto prune tests/ci/
```

## Behaviour

- Runs pytest with `--ditto-prune` flag
- Tracks which snapshot files are accessed during the run
- Deletes any snapshot files that were not accessed

!!! warning
    Using `-k` for a partial run may falsely classify snapshots for un-run
    tests as unused. Only use prune with a full test run to avoid accidental
    deletion.

!!! note
    Prune needs a single process. Under pytest-xdist (`-n N`) it fails the run
    and deletes nothing; if your `addopts` sets `-n`, run `ditto prune -n 0`.
    See [Running under pytest-xdist](../guides/lock-file.md#running-under-pytest-xdist).
