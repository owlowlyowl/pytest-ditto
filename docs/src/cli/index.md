# CLI Reference

The `ditto` command provides snapshot management tools independent of a test run.

## Commands

| Command | Description |
|---------|-------------|
| [`ditto run`](run.md) | Run pytest with snapshot reporting |
| [`ditto update`](update.md) | Regenerate all snapshots |
| [`ditto prune`](prune.md) | Remove stale snapshots |
| [`ditto list`](list.md) | List all snapshot files |
| [`ditto status`](status.md) | Show aggregate statistics |
| [`ditto clean`](clean.md) | Delete all `.ditto/` directories |
| [`ditto recorders`](recorders.md) | List registered recorder plugins |
| [`ditto doctor`](doctor.md) | Run health checks |
| [`ditto lint`](lint.md) | Check snapshots for issues |
| [`ditto stats`](stats.md) | Per-directory usage breakdown |

## CLI and Remote Backends

`ditto list`, `status`, `stats`, and `lint` work with remote and registered
backends, not just local `file://` snapshots.

To stay correct in the presence of per-test `record(target=...)` marks and
fixture-defined profiles, these commands always run an internal
`pytest --setup-only` pass. The real `ditto_target_profiles` /
`ditto_storage_options` fixtures resolve each backend.

This means these commands:

- Import your test modules
- Need the same runtime credentials your test run needs
- Are slower than a plain directory listing even for local-only projects

`ditto clean` remains local-only and never touches remote snapshots.
