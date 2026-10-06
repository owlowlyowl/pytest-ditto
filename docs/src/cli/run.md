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
- After the run, the ditto session report counts the snapshots created,
  rewritten and not written (its backend write raised), then lists each one by
  key and recorder under its test file and test. It also says whether
  `ditto.lock` was written (entries added and removed), refused or failed. Running `pytest`
  directly prints the same report. Under `--ditto-prune` it also lists each
  snapshot pruned or not pruned; under `--ditto-prune-dry-run`, each it would
  prune. A run that changed nothing prints no report, and neither does a run
  under pytest-xdist distribution (`-n`), whose controller runs no tests.
  When `ditto lock` replaces a `ditto.lock` it couldn't read, the report says
  the previous entries are unknown rather than counting them.
