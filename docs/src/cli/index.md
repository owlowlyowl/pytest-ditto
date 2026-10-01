# CLI Reference

The `ditto` command provides snapshot management tools independent of a test run.

## Commands

| Command | Description |
|---------|-------------|
| [`ditto run`](run.md) | Run pytest with snapshot reporting |
| [`ditto update`](update.md) | Regenerate all snapshots |
| [`ditto prune`](prune.md) | Remove stale snapshots |
| [`ditto verify`](verify.md) | Fail if the backend drifted from `ditto.lock` |
| [`ditto list`](list.md) | List every snapshot, grouped by target and test file |
| [`ditto status`](status.md) | The inventory's one summary |
| [`ditto clean`](clean.md) | Delete all `.ditto/` directories |
| [`ditto recorders`](recorders.md) | List registered recorder plugins |
| [`ditto doctor`](doctor.md) | Run health checks |
| [`ditto lint`](lint.md) | Check snapshots for issues |
| [`ditto stats`](stats.md) | Where the snapshots live: a row per target |

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
as `—`); use `--live` for those. See [The Lock File](../guides/lock-file.md).

`ditto clean` remains local-only and never touches remote snapshots.

## How ditto names a snapshot

Every command names a snapshot the same way: the node ID of the test that
owns it, its key, and its recorder — the three facts `ditto.lock` records.
A snapshot the lock doesn't record (an orphan, or one recorded since the
last `ditto lock`) has no identity to show, so it is named by the label in
its stored name and marked `not in lock`.

A local target is shown as a path relative to the current directory, never
an absolute one; a remote URI is shown whole. Every view is a table or panel
built to fit the terminal width — below 60 columns a snapshot's key and
recorder move under its name, below 80 the size and date share a cell — and
a long name wraps in the middle rather than being truncated, so the part that
tells two rows apart stays visible. `ditto list --flat` gives one row per
snapshot with the whole node ID, for `grep` and scripts.
