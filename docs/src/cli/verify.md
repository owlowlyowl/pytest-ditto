# ditto verify

Checks the live backend against the committed `ditto.lock` and fails when they
have drifted. Read-only — it never writes snapshots or the lock. Intended for CI.

See [The Lock File](../guides/lock-file.md) for the model.

## Usage

```
ditto verify [PYTEST_ARGS]
```

`ditto verify` re-runs your suite with `--ditto-verify`; extra arguments are
passed through to pytest.

## Examples

```bash
# Fail CI if the backend has drifted from ditto.lock
ditto verify

# Verify a subset (only the exercised targets are checked)
ditto verify tests/ci/
```

## What it reports

| Drift | Meaning |
|---|---|
| missing | Recorded in `ditto.lock` but absent from the backend. |
| orphan | Present in the backend (under an owned prefix) but not in the lock. |
| unsynced | Produced this run but not yet in the lock — run `ditto lock`. |

Any drift, a missing or corrupt lock, or an unreachable target fails the run
(non-zero exit). A filtered run (`-k`/`-m`) warns that it only checked the
exercised targets. `--ditto-verify` cannot be combined with the write flags
(`--ditto-update` / `--ditto-lock` / `--ditto-prune` / `--ditto-prune-dry-run`).
