# ditto run

Runs pytest and reports snapshot activity via the ditto session report. Any
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

- Forwards all arguments to `pytest` and exits with its status
- After the run, the ditto session report lists each snapshot created,
  updated or not written (its backend write raised), and whether `ditto.lock`
  was written (entries added and removed), refused or failed. Running `pytest`
  directly prints the same report. Under `--ditto-prune` it also lists each
  snapshot pruned or not pruned; under `--ditto-prune-dry-run`, each it would
  prune. A run that changed nothing prints no report.
