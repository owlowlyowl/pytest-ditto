Phase-1 lock-file bug fixes, cherry-picked onto current `main` (Phase 1 itself already landed via #88, so this is just the remaining delta — the bug batch).

Closes #82
Closes #83
Closes #84
Closes #85

## What this fixes

- **#82 — path/nodeid narrowing.** `_is_authoritative_run` now refuses positional path/nodeid args (`config.option.file_or_dir`) instead of truncating entries for un-collected files in a shared target. The `getattr` checks are flattened to a single `any(narrowing)`; the considered alternative (module-scoped preservation) is recorded in a code comment. `ditto lock`'s CLI help is updated to drop the path example.
- **#83 — xdist.** `_xdist_is_distributing` guard: under `-n`, `--ditto-lock` hard-fails (the controller has no observations) and the append path warns it isn't maintained. Detection is unit-tested (xdist is not a dependency, so the distributed-controller branch has no end-to-end test — noted follow-up).
- **#85 — corrupt-lock recovery.** `_rewrite_lockfile` now recovers a corrupt `ditto.lock` by warning and rebuilding from scratch (`existing = None`) rather than aborting.
- **`_fail_session`.** All explicit-command refusals (`--ditto-lock` under `-k`/`-m`, path narrowing, or xdist) now exit non-zero rather than warning-and-exiting-0.
- **#84 — phantom entries.** The core fix (record the lock entry only after a successful write) was already on `main` via #88; this PR strengthens its test to assert the failing run actually failed.

## Validation

- Full `tests/ci` suite green on **py312 and py313** (290 passed, 2 skipped, 2 xfailed).
- New CI gates pass: **ruff-check** and **basedpyright** (0 errors, 0 warnings).

Design tracking: #80. These unblock #79 (Phase 2 / verify).
