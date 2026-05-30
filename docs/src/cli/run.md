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

- Forwards all arguments to `pytest`
- After the test run completes, displays a summary of snapshot activity:
  created, updated, and unused snapshots
