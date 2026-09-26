# ditto doctor

Runs health checks: verifies pytest is available, the ditto pytest plugin is
registered, and all registered recorder plugins load successfully.

## Usage

```
ditto doctor
```

## Behaviour

Checks:

- pytest is installed and importable
- The ditto pytest plugin is registered and imports cleanly. The check fails if
  another installed plugin claims the same `pytest11` entry-point name, because
  pytest loads only one plugin per name and silently skips the others.
- All registered recorder plugins (`ditto_recorders`) load without error

Reports any issues found and exits non-zero if health checks fail.
