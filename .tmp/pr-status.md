> ## ✅ Phase 1 implemented (produce & maintain the lock file)
>
> This branch delivers **Phase 1** of the design below: everything needed to *generate and maintain* `ditto.lock`. The consumers — authoritative prune, `verify`, and the lightweight CLI inventory — are deferred to follow-up phases (see "Notes for plans 006 / 007").
>
> **What shipped**
> - `src/ditto/_lockfile.py` — `msgspec.Struct` model (`LockEntry`/`LockTarget`/`LockFile`), deterministic version-validated `serialise`/`deserialise`, atomic `read_lockfile`/`write_lockfile`, `portable_target_id`, `storage_key`, append-only `merge_append`.
> - `src/ditto/snapshot.py` — `LockSeen`; `_SessionTracker.lock_created`/`lock_accessed`; `Snapshot.nodeid`/`target_id`; `resolve_snapshot` records observations.
> - `src/ditto/plugin.py` — fixture stamps `nodeid`/`target_id`; **append-only** lock write on normal runs; **`--ditto-lock`** authoritative rebuild (full-run gated via `_is_authoritative_run`, snapshot values untouched); `.gitignore` guard; xdist-worker guarded; every write failure only warns.
> - `src/ditto/cli.py` — `ditto lock` command. `pyproject.toml` — `msgspec>=0.18`.
> - Tests: `tests/ci/test_lockfile.py` (24 unit), `tests/ci/test_lockfile_session.py` (8 pytester integration).
>
> **Verification:** full `tests/ci` suite green on **py312 and py313** (285 passed, 2 skipped, 2 xfailed each); `ruff check` and `ty` clean on the new/changed code.
>
> **Lifecycle (lockfile-governed, like `package-lock.json`):** normal runs *append* new entries only; removal happens solely via an explicit, full-run `ditto lock` / `--ditto-lock`; CI verification and lock-file-first CLI inventory come in Phase 2/3.
>
> **Open follow-ups for Phase 2** (captured in the plan): assert `storage_key`'s nodeid→module reconstruction round-trips against the live `SnapshotKey.module`; add parametrised/class-based session coverage; decide whether ditto warnings should use a dedicated category (to survive `filterwarnings = ["ignore::UserWarning"]`) and whether a refused `ditto lock` should exit non-zero.
>
> _The full design follows._
>
> ---
>
