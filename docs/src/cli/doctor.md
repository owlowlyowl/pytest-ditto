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
- Recorder registrations keep the plugin contract: valid names, no name
  registered twice, no two recorders sharing an identifier, no bare name that
  is also a namespace, no name shadowing a `ditto` attribute, and no installed
  plugin still on the 1.x contract. Each problem is one failing
  `plugin contract` row.

Reports any issues found and exits non-zero if health checks fail.
