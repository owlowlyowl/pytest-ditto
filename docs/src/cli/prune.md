# ditto prune

Removes stale snapshots by running pytest with `--ditto-prune`: snapshots in the
backend that `ditto.lock` doesn't record are deleted.

## Usage

```
ditto prune [--check] [--shared] [PATH] [PYTEST_ARGS...]
```

| Option | Effect |
|---|---|
| `--check` | Report what would be deleted without deleting it (`--ditto-prune-dry-run`). |
| `--shared` | Also delete from targets that might be shared (`--ditto-prune-shared`). |

## Examples

```bash
# Prune all stale snapshots
ditto prune

# List what would be pruned
ditto prune --check

# Prune a remote target that this project and branch use alone
ditto prune --shared
```

## Behaviour

- Runs pytest with `--ditto-prune`, then compares each target the run used with
  `ditto.lock`.
- Deletes each snapshot the lock doesn't record, under the test modules the
  suite owns. A snapshot created during the same run is never deleted; run
  `ditto lock` to record it. Snapshots this run created but the lock doesn't
  record, and keys the lock records but the backend lacks, are each reported
  against the target that holds them.
- The session report groups each deleted snapshot under the target it was
  deleted from, so a suite with several backends can tell them apart.
- Needs a `ditto.lock`; without one it deletes nothing and fails.
- Fails the run if it can't finish: a target it can't read (with `--check`
  too), or a snapshot it couldn't delete. It still processes the other
  targets, then says how many snapshots it deleted from each target and which
  ones it couldn't, with the error.
- Deletes nothing from a target that other checkouts might share (a remote URI,
  or a `file://` path outside the project, after following symlinks) unless
  you pass `--shared`. Without
  it, the run fails and says how many snapshots it left there. Pass `--shared`
  only when each project and branch has its own target path: another branch's
  snapshots look like orphans. See
  [Sharing a target](../guides/lock-file.md#sharing-a-target).

!!! warning
    Using `-k` for a partial run may falsely classify snapshots for un-run
    tests as unused. Only use prune with a full test run to avoid accidental
    deletion.

!!! note
    Prune needs a single process. Under pytest-xdist distribution (`-n N`, or
    `--dist` with `--tx`) it stops with a usage error before running any tests
    and deletes nothing; if your `addopts` sets `-n`, run `ditto prune -n 0`.
    See [Running under pytest-xdist](../guides/lock-file.md#running-under-pytest-xdist).
