### Summary

`--ditto-prune` (and the "unused" report) decides a snapshot is stale by set-difference against **what the current session accessed**, in `pytest_sessionfinish` (`src/ditto/plugin.py:705`). That is only correct when the run exercised *every* test that owns data in the backend. Any run that is not authoritative over the backend's keyspace can delete legitimate snapshots.

### Mechanism

Pass 1 computes `not_accessed = owned_keys − accessed_keys` and deletes it. `owned_keys` is filtered to the *module* prefixes the session touched (`_keys_for_modules`), which fixed the worst cross-module case but leaves the authority signal — "not accessed this session" — fundamentally wrong.

### Problems

- **P1 — Partial selection within a run module** (`-k`, `-m`, explicit node ids): a deselected sibling test's snapshot is in `owned_keys`, never accessed, and gets pruned.
- **P2 — Failed/errored tests:** a test that errors *before* calling `snapshot(...)` never records access, so a valid baseline is pruned because the test happened to fail this run.
- **P3 — Shared/remote backends** (S3, Redis, Postgres, shared `memory://`/`file://`): the store legitimately holds keys for tests not in this run; Pass 1 sees them as unused.
- **P4 — Unhashable `storage_options`** disable the backend cache (`plugin.py:186`), producing distinct backend objects for one shared target and reopening within-module cross-deletion.
- **P5 — Weak partial-run detection:** the only guard is a single `-k` string check in `cli.py:315`; it misses path narrowing, `-m`, `--lf/--ff`, `--deselect`, `-x`, node ids, and xdist shards.
- **P6 — The destructive step is non-atomic and unreviewable:** Pass 1 enumerates then per-key deletes with errors swallowed; the user never sees a diff before deletion, and a partially-completed prune leaves an inconsistent store.

### Impact

Silent data loss: the report says "N pruned" with no error. The destructive direction is exactly the one that should be safest.

### Why it can't be fixed with the current signal

"Accessed this session" cannot distinguish *"legitimate but not run this time"* from *"orphaned."* Settling that requires a record of what is legitimate that is independent of which tests ran.
