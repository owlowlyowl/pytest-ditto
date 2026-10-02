# ditto run

Runs pytest and reports what happened to snapshots and `ditto.lock`. Any
extra arguments are forwarded directly to pytest.

## Usage

```
ditto run [PATH] [PYTEST_ARGS...]
```

## Examples

```bash
# Run all tests
ditto run

# Run specific directory
ditto run tests/ci/

# Run with filter
ditto run tests/ci/ -k test_foo
```

## Behaviour

- Forwards all arguments to `pytest`, whose own output is unchanged
- After the run, prints one Ditto report: each snapshot created, rewritten or
  that failed to write, then whether `ditto.lock` was written, unchanged,
  refused or failed. `ditto update`, `ditto lock` and `ditto prune` print the
  same report; prune also lists each snapshot it deleted, failed to delete or
  would delete.
- Exits with pytest's exit status. If pytest doesn't report its outcomes (for
  example under `pytest-xdist`), the report says they're unknown.
- On Ctrl-C, pytest finishes its session (lock write, deletions) and the report
  shows what completed; a second Ctrl-C stops it at once.
