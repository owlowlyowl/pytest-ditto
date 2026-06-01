# CLI Reference

The `ditto` command provides snapshot management tools independent of a test run.

## Commands

| Command | Description |
|---------|-------------|
| [`ditto run`](run.md) | Run pytest with snapshot reporting |
| [`ditto update`](update.md) | Regenerate all snapshots |
| [`ditto prune`](prune.md) | Remove stale snapshots |
| [`ditto verify`](verify.md) | Fail if the backend drifted from `ditto.lock` |
| [`ditto list`](list.md) | List all snapshot files |
| [`ditto status`](status.md) | Show aggregate statistics |
| [`ditto clean`](clean.md) | Delete all `.ditto/` directories |
| [`ditto recorders`](recorders.md) | List registered recorder plugins |
| [`ditto doctor`](doctor.md) | Run health checks |
| [`ditto lint`](lint.md) | Check snapshots for issues |
| [`ditto stats`](stats.md) | Per-directory usage breakdown |

## CLI and remote backends

`ditto list`, `status`, `stats`, and `lint` are **credential-free by default**.
Local snapshots are read straight from the filesystem; remote snapshots are read
from the committed `ditto.lock`. No test modules are imported and no backend
credentials are needed — even for projects with remote or fixture-defined
targets, because the lock already records every resolved target from past runs.

Pass `--live` to read the live backends instead (an internal `pytest --setup-only`
pass that resolves real fixtures and per-test `record(target=…)` marks). `--live`
imports your test modules and needs the same credentials your test run needs.

Remote snapshots read from the lock have no physical size or modified date (shown
as `—`); use `--live` for those. See [The Lock File](../guides/lock-file.md).

`ditto clean` remains local-only and never touches remote snapshots.
