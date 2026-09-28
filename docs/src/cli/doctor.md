# ditto doctor

Runs health checks: verifies pytest is available, the ditto pytest plugin is
registered, and all registered recorder and backend plugins load
successfully.

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
  registered twice (and so no two recorders sharing snapshot files), no bare name that
  is also a namespace, no name shadowing a `ditto` attribute, and no installed
  plugin still on the 1.x contract. Each problem is one failing
  `plugin contract` row.
- All registered backend plugins (`ditto_backends`) load without error, each
  as a `backend: <scheme>` row
- Backend registrations use valid, lowercase URI schemes, register no scheme
  twice, and don't register `file`, which ditto handles itself. Each problem is
  one failing `backend contract` row.

Reports any issues found and exits non-zero if health checks fail.
