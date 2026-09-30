# ditto lock

Rebuilds `ditto.lock` from the snapshots exercised by a complete pytest run.
Snapshot values are unchanged. Use it to refresh the declared inventory after
changing tests or snapshot targets.

## Usage

```bash
ditto lock [PYTEST_ARGS]
```

This runs pytest with `--ditto-lock` and preserves pytest's exit status.
The suite must run in full: positional test paths or node IDs and selection
filters are rejected because a partial rebuild could remove other tests'
entries. Configure the intended suite scope with pytest's `testpaths` setting.

```bash
# Rebuild the lock from the complete suite
ditto lock
```

The run needs access to the configured backends and their credentials.
See [The Lock File](../guides/lock-file.md) for the lock's lifecycle and
restrictions, including running under pytest-xdist.
