## Phase 1: produce & maintain `ditto.lock`

**Full design:** #80 (Lock file: design spec & phase tracking)
**Contributes to:** #76 (authoritative prune — Phase 3), #77 (lightweight CLI — Phase 4), #79 (verify — Phase 2)
**Fixes (Phase-1 bug batch):**

Closes #82
Closes #83
Closes #84
Closes #85

---

### What shipped

- `src/ditto/_lockfile.py` — `msgspec.Struct` model (`LockEntry`/`LockTarget`/`LockFile`), deterministic version-validated `serialise`/`deserialise`, atomic `read_lockfile`/`write_lockfile`, `portable_target_id`, `storage_key`, append-only `merge_append`.
- `src/ditto/snapshot.py` — `LockSeen`; `_SessionTracker.lock_created`/`lock_accessed`; `Snapshot.nodeid`/`target_id`; `resolve_snapshot` records observations.
- `src/ditto/plugin.py` — fixture stamps `nodeid`/`target_id`; **append-only** lock write on normal runs; **`--ditto-lock`** authoritative rebuild (full-run gated via `_is_authoritative_run`, snapshot values untouched); `.gitignore` guard; xdist-worker guarded; every write failure only warns.
- `src/ditto/cli.py` — `ditto lock` command. `pyproject.toml` — `msgspec>=0.18`.
- **Phase-1 bug batch (#82–#85):** record lock entries only after a successful write (no phantom entries, #84); refuse path/nodeid-narrowed (#82) and xdist (#83) `--ditto-lock`; recover a corrupt lock on rebuild (#85); explicit refusals exit non-zero (`_fail_session`).
- Tests: `tests/ci/test_lockfile.py` (24 unit), `tests/ci/test_lockfile_session.py` (12 pytester integration).

### Verification

Full `tests/ci` suite green on **py312 and py313** (290 passed, 2 skipped, 2 xfailed each); `ruff check` and `ty` clean on the new/changed code.

### Lifecycle (lockfile-governed, like `package-lock.json`)

Normal runs *append* new entries only; removal happens solely via an explicit, full-run `ditto lock` / `--ditto-lock`; CI verification and lock-file-first CLI inventory come in subsequent phases (see #80).

### Open follow-ups (decided in Phase 2 design, see #80)

- ✅ `_fail_session`: `--ditto-lock` refusal now exits non-zero (landed in the Phase-1 bug batch above).
- `DittoWarning(UserWarning)`: all ditto `warnings.warn` calls get a dedicated category. Lands in Phase 2.
- Storage-key round-trip assertion (`storage_key` nodeid→module reconstruction). Lands in Phase 2.
- Parametrised/class-based session coverage. Lands in Phase 2/3.
