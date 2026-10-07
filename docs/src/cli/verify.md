::: mkdocs-click
    :module: ditto.cli._pytest
    :command: cmd_verify
    :prog_name: ditto verify
    :style: plain

## How it runs

`ditto verify` re-runs your suite with `--ditto-verify`; extra arguments are
passed through to pytest. See [The Lock File](../concepts/lock-file.md) for the model.

## Examples

```bash
# Fail CI if the backend has drifted from ditto.lock
ditto verify

# Verify a subset (only the exercised targets are checked)
ditto verify tests/ci/
```

## What it reports

| Drift | Meaning | Fix |
|---|---|---|
| missing | Recorded in `ditto.lock` but absent from the backend. | `ditto run` records it again; `ditto lock` drops it if its test is gone. |
| orphan | Present in the backend (under an owned prefix) but not in the lock. On a target another branch or project also writes to, its snapshots are reported here too; see [Sharing a target](../concepts/lock-file.md#sharing-a-target). | `ditto prune` deletes it (`ditto prune --check` to preview). |
| unsynced | Produced this run but not yet in the lock. | `ditto lock` records it. |

Drift is grouped by the target that holds it, so a suite with several backends
can tell which one needs attention — two targets can hold the same storage key.
A key the lock records is named by its test's node ID and key; a key the lock
doesn't record (an orphan or an unsynced one) is named by its storage name.

Each kind of drift ends with a `fix:` line saying how to resolve it.

When there is no drift, it names the targets it checked:
`ditto verify: no drift in 1 target: tests/.ditto`. A run that used no snapshot
target says so instead, since it checked nothing; it still passes.

Verify checks that storage and the lock agree, not that snapshot values are
right: the tests' own assertions do that.

Any drift, a missing or corrupt lock, or an unreachable target fails the run
(non-zero exit). An unreachable target is named, with a note that its snapshots
weren't checked. A filtered run (`-k`/`-m`) warns that it only checked the
exercised targets. `--ditto-verify` cannot be combined with the write flags
(`--ditto-update` / `--ditto-lock` / `--ditto-prune` / `--ditto-prune-dry-run`).

`ditto verify` needs a single process. Under pytest-xdist distribution
(`-n N`, or `--dist` with `--tx`) it stops with a usage error before running any
tests; if your `addopts` sets `-n`, run `ditto verify -n 0`.
See [Running tests in parallel](../guides/ci.md#running-tests-in-parallel).
