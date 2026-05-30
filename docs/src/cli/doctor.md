# ditto doctor

Runs health checks: verifies pytest is available and all registered plugins
loaded successfully.

## Usage

```
ditto doctor
```

## Behaviour

Checks:

- pytest is installed and importable
- All registered recorder plugins load without error
- All registered backend plugins load without error

Reports any issues found and exits non-zero if health checks fail.
