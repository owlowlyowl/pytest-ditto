## Phase 2: verify + diff engine

**Full design:** #80 · **Closes #79.** Builds on Phase 1 (`ditto.lock`) + the #82–#85 bug batch, both on `main`.

Adds a read-only CI guard — `--ditto-verify` / `ditto verify` — that fails a run when the live backend has drifted from the committed `ditto.lock`, on a pure shared diff engine that Phase 3 (prune) will reuse.

### What shipped

- **`src/ditto/_reconcile.py` (new):** pure `diff_backend(lock_keys, backend_keys, owned) -> ReconcileResult(missing, orphan)` + `owned_prefixes(modules, scheme)`. No I/O; owned-prefix scoping ignores other suites'/branches' keys on shared backends.
- **`src/ditto/exceptions.py`:** `DittoWarning(UserWarning)` — every `warnings.warn` in ditto (across `plugin.py` and the recorder/backend plugin loaders) now carries `category=DittoWarning`, so advisories can be silenced/escalated independently. Load-bearing signals (verify drift, refusals) are hard failures, not warnings.
- **`src/ditto/snapshot.py`:** `_SessionTracker.target_backends` (target_id → live backend) for verify enumeration; a `Snapshot.readonly` mode (see below).
- **`src/ditto/plugin.py`:** `--ditto-verify` option; `_run_verify`/`_verify_target` + report; at session finish, diffs each exercised target and `_fail_session`s on **missing** (in lock, gone from backend), **orphan** (in backend, not in lock), or **unsynced** (produced this run, not in lock). No-lock and corrupt-lock fail loudly; a partial (`-k`/`-m`) run warns it only checked exercised targets. A `pytest_configure` guard rejects `--ditto-verify` with any write flag (`--ditto-update`/`--ditto-lock`/`--ditto-prune`).
- **`src/ditto/cli.py`:** `ditto verify` (shells out to `pytest --ditto-verify`).

### Design note: read-only mode

Verify runs *after* the tests execute. Without suppressing writes, a test would silently **recreate** a deleted snapshot before the check, making "missing" detection falsely green. So `--ditto-verify` puts snapshots in `readonly` mode (`resolve_snapshot` records observations but never writes). A test asserts the read-only guarantee directly (deleted snapshot stays absent; lock untouched).

### Validation

- Full `tests/ci` suite green on **py312 and py313** (312 passed, 2 skipped, 2 xfailed each); **ruff-check** and **basedpyright** CI gates clean.
- Each task went through implementer + spec + code-quality review; the read-only addition (beyond the original plan) was independently validated as required, correct, and minimal.

### Deferred follow-ups

- Move `_verify_target`'s drift-classification into `_reconcile.py` when Phase 3's prune co-consumes it (so the shared interface is designed for both).
- xdist: verify is single-process only (inherits the library's existing limitation, #83); no distributed integration test (xdist isn't a dependency).
