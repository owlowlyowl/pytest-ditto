# CLI Reference

The `ditto` command provides snapshot management tools independent of a test run.

## Commands

| Command | Description |
|---------|-------------|
| [`ditto run`](run.md) | Run pytest, passing every argument through |
| [`ditto update`](update.md) | Re-record snapshots from current output |
| [`ditto verify`](verify.md) | Run the suite read-only and fail if storage and `ditto.lock` disagree |
| [`ditto lock`](lock.md) | Rebuild `ditto.lock` from a full run |
| [`ditto prune`](prune.md) | Delete stored snapshots `ditto.lock` doesn't record |
| [`ditto list`](list.md) | List snapshots with their test, key, recorder, size and date |
| [`ditto status`](status.md) | Show totals, broken down by recorder |
| [`ditto stats`](stats.md) | Show snapshot count, size and recorders per target |
| [`ditto lint`](lint.md) | Check for malformed names, unknown recorders and empty files |
| [`ditto recorders`](recorders.md) | List installed recorders and their marks |
| [`ditto doctor`](doctor.md) | Check that ditto and its plugins are installed correctly |
| [`ditto clean`](clean.md) | Delete `.ditto/` directories |

The commands that run tests (`run`, `update`, `verify`, `lock`, `prune`) pass
any other arguments through to pytest, so `-k`, `-x` and paths work as usual.
Each page's usage and options are generated from the command itself, and match
`ditto <command> --help`.

Run `ditto --version` to print the installed pytest-ditto version (include it
in bug reports).

## CLI and remote backends

`ditto list`, `status`, `stats`, and `lint` are **credential-free by default**.
Local snapshots are read straight from the filesystem; remote snapshots are read
from the committed `ditto.lock`. No test modules are imported and no backend
credentials are needed — even for projects with remote or fixture-defined
targets, because the lock already records every resolved target from past runs.

Pass `--live` to read the live backends instead (an internal `pytest --setup-only`
pass that resolves real fixtures and per-test `record(target=…)` marks). `--live`
imports your test modules and needs the same credentials your test run needs.
If a backend can't be read (unreachable, or the credentials are wrong), the
command still shows the backends it could read, then names each one it couldn't
with the error and exits 1, so a partial inventory never passes for a complete
one.

Remote snapshots read from the lock have no physical size or modified date (shown
as `—`); use `--live` for those. See [The Lock File](../concepts/lock-file.md).

`ditto clean` remains local-only and never touches remote snapshots.
