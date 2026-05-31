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
Closes #76
Closes #77

Introduces a **lock file** (`ditto.lock`) — a tool-generated, committed, PR-reviewed file that is the source of truth for which snapshots are legitimate. Modelled on `package-lock.json` / `Cargo.lock` / `poetry.lock`. One artifact addresses both linked issues: prune compares the live backend against it (authoritative on any run), and the CLI renders inventories directly from it (credential-free, no pytest spawn).

> This PR is an empty placeholder opened for design review. The full design follows; implementation will land as subsequent commits.

**Affects:** `src/ditto/plugin.py` (prune/report hooks, fixture), `src/ditto/cli.py` (inventory dispatch, new commands), `src/ditto/snapshot.py` (`_SessionTracker`), a new `src/ditto/_lockfile.py`, docs, and CI coverage.

---

## Problem

pytest-ditto has two coupled weaknesses that share a single root cause.

**1. Prune is not authoritative (#76).** `pytest_sessionfinish` decides a snapshot is "unused" by set-difference against *what this session accessed* (`plugin.py:705`). That is only correct when the run exercised every test that owns data in the backend. See #76 P1–P6 for the concrete failure modes (partial selection, failed tests, shared/remote backends, unhashable options, weak partial-run detection, and a non-atomic unreviewable delete).

The module-level ownership filter (`_keys_for_modules`) mitigated the worst cross-module case but cannot fix any of the above, because "not accessed this session" is the wrong authority signal.

**2. CLI introspection is heavyweight (#77).** `list`, `status`, `stats`, and `lint` always spawn an internal `pytest --setup-only --ditto-introspect` pass (`cli.py:98`, `_cli_introspect.py`). Even a default local-only project pays a full pytest-startup cost just to list files, and remote backends require live credentials merely to render an inventory.

**Root cause (shared):** there is no persisted, credential-free record of *which snapshots are legitimate* that is independent of which tests ran this session.

---

## Goals

- Make prune authoritative on any run — partial, failed, parallel, or against a shared/remote backend — by deciding legitimacy from a committed record rather than session access.
- Give the read-only CLI commands a fast, credential-free, remote-capable inventory source so the `pytest --setup-only` pass becomes opt-in.
- Never persist credentials. Never silently destroy data.
- Keep the change non-breaking: the feature is opt-in and existing projects keep working with no lock file present.

## Non-Goals

- True pytest-xdist support (multi-process aggregation of `_SessionTracker`). The lock file *inherits* the library's existing single-process assumption; it does not fix it. Consistent with `design-cli-remote-backends.md` non-goals.
- Content-level verification / hashing of snapshot values. Content correctness is already enforced by the test assertion itself.
- Remote `clean` (still local-only).
- Per-key selective update or snapshot approval workflows.

---

## Solution Overview

Introduce a **lock file** — a tool-generated, committed, PR-reviewed file (`ditto.lock`) that is the source of truth for which snapshots are legitimate. Modelled on `package-lock.json` / `Cargo.lock` / `poetry.lock`: never hand-edited, deterministic, merge-friendly, and reviewed as part of the diff.

The lock file is **authoritative and committed** (not a derived cache): a disposable cache cannot survive a fresh CI checkout and so cannot carry prune authority. One artifact serves both problems — prune compares the live backend against it, and the CLI renders inventories directly from it.

### Authority and lifecycle (decided)

- **Authoritative & committed**, lockfile-governed: tool-written only, deterministic, reviewed in PRs.
- **Auto-append on normal runs; removal only via explicit reviewed action.** Ordinary `pytest` runs may *add* entries for newly-created snapshots but never remove. Removal happens only through `ditto update` / `ditto lock` on a full authoritative run.
- **Namespace-scoped.** A target's entries define the module prefixes this project owns for that target. Every destructive operation is constrained to those prefixes, so on a shared remote backend prune can never touch another branch's or suite's keys.
- **CI verifies, it does not rewrite** (see `verify`).

---

## Architecture & Data Model

### Module layout

A new module **`src/ditto/_lockfile.py`** owns the committed artifact and its (de)serialization. It is distinct from `_manifest.py`: the *manifest* is live backend state (sizes, mtimes) produced by an introspection pass; the *lock file* is committed identity — the source of truth.

### File

A single **`ditto.lock`** at the pytest `rootdir` (Approach A: one project-root lock file). JSON, deterministically sorted, one entry per line within arrays so diffs and merges stay clean.

### Portable identities

The lock file is machine-independent and never stores runtime-absolute paths. Absolute resolution happens at runtime via the existing `_canonicalize_uri(test_dir)`.

- **Target id:** for `file://`, the rootdir-relative posix path (`tests/api/.ditto`); for remote, the URI verbatim (`s3://bucket/ci-snapshots`).
- **Entry identity:** `(nodeid, key, recorder)` — e.g. `tests/test_api.py::TestX::test_foo`, `"result"`, `"pkl"`. The *storage key* (`module.group@key.ext` for file, `module/group@key.ext` for remote) is **derived** from these via the existing `SnapshotKey` / `_flat_key` logic, never stored. This keeps the lock file format-agnostic and lets storage-key derivation evolve without a lock-file migration.

```json
{
  "version": 1,
  "targets": {
    "tests/api/.ditto": {
      "scheme": "file",
      "entries": [
        {"nodeid": "tests/test_api.py::test_create", "key": "headers", "recorder": "json"},
        {"nodeid": "tests/test_api.py::test_create", "key": "payload", "recorder": "json"}
      ]
    },
    "s3://bucket/ci-snapshots": {
      "scheme": "s3",
      "entries": [
        {"nodeid": "tests/test_etl.py::test_pipeline", "key": "frame", "recorder": "pandas.parquet"}
      ]
    }
  }
}
```

**Deliberately excluded:** sizes, mtimes, content hashes — they churn on every value change and are not identity. CLI sizes come from a local `stat` (file://) or are `—` (remote), as today.

### Robustness property

Each entry stores the recorder as its *ext string*, not a live `Recorder`. So storage keys derive (and prune/verify/list work) even when the plugin that produces that format is not installed; the live recorder is only needed to *load values*.

---

## Operational Flows

The unifying rule: **legitimacy is defined by the committed lock file, never by which tests ran this session.**

### 1. Append (every normal `pytest` run; `pytest_sessionfinish`)

- When `resolve_snapshot` *creates* a snapshot (record-on-first-run), `_SessionTracker` records `(target_id, nodeid, key, recorder)` alongside the `SnapshotKey` it already tracks. The `snapshot` fixture supplies `target_id` when it registers the backend.
- At session finish: **load the existing `ditto.lock`, union in this session's created entries, write back only if changed** (sorted; no spurious churn).
- **Invariant: append-only.** A normal run never removes an entry, so a partial or failed run can only add legitimate keys — it can never corrupt the lock file.

### 2. Update / lock (`ditto update`, and `ditto lock`)

The only operations that may **remove** entries; both gated on a full authoritative run (refuse to rewrite under `-k`/`-m`/node ids/`testsfailed > 0`; fall back to append-only with a warning).

- **`ditto update`** (full run, `--ditto-update`): re-records snapshot *values* and rewrites each exercised target's entries to exactly the run's accessed-or-created set. Entries for deleted/renamed tests disappear.
- **`ditto lock`** (full run, non-destructive): regenerates `ditto.lock` from current snapshots **without rewriting any values**. The bootstrap/adoption and identity-reconcile path. Mirrors `poetry lock` / `cargo generate-lockfile`.

### 3. Prune (`ditto prune`, or in-session `--ditto-prune`)

- Compares **live backend keys within owned prefixes** against the lock file; orphans = backend keys under an owned prefix with no lock entry. Deletes orphans only.
- Because authority is the lock file, **in-session `--ditto-prune` is correct on partial runs**: it prunes only targets the run actually opened, and within those deletes strictly what the lock file says is illegitimate — never what merely wasn't accessed. A failed/deselected test can no longer cause deletion.
- **`ditto prune` (CLI) is two-phase:** a dry-run pass enumerates the backend (introspection pass for remote; direct stat for local), diffs against the locally-read lock file, prints the orphan list; on confirmation a second pass deletes. Reviewable, never silently destructive.
- Owned-prefix scoping protects shared remote stores: keys outside this project's namespace are invisible to prune.

### 4. Verify (`ditto verify`, or `--ditto-verify`; the CI guard)

Read-only. For each exercised target, assert backend-within-owned-prefixes equals the lock file:

- lock entry whose key is **missing** from the backend → fail ("snapshot not committed / out of sync").
- backend key under an owned prefix **not** in the lock file → fail ("drift / lock file not synced").
- a collected test that *creates* a key absent from the lock file → fail ("lock file out of date — run `ditto lock`").

This is the precise, lock-file-backed version of the `ci_mode` guard from `snapshot-lifecycle.md`: it removes the "first green CI run silently records a wrong baseline" footgun the README currently warns about.

---

## CLI Integration (lightweight introspection)

`_inventory_or_exit` (`cli.py:98`) becomes **lock-file-first**:

- If `ditto.lock` exists → render directly from it. **No pytest spawn, no credentials**, and it works for remote backends (the only credential-free inventory source remote backends have ever had).
- A `--live` flag opts into the existing introspection pass to enrich with real backend state (sizes, mtimes) or reconcile against what's actually stored.
- If `ditto.lock` is absent (pre-adoption) → fall back to today's behavior and hint the user to run `ditto lock`.

| Command | From lock file (instant) | Needs backend (`--live` only) |
|---|---|---|
| `list` | test, key, recorder, per target | size / modified (local stat; remote `—`) |
| `stats` / `status` | counts, by-recorder breakdown | total size (local stat; remote `—`) |
| `lint` | unknown-recorder, malformed-name | empty-file / missing-value (fold into `verify`) |

**Unchanged:** `clean` (local-only), `doctor`, `recorders`; `run`/`update`/`prune` still shell out to pytest (`prune` now lock-file-authoritative).

---

## Error Handling

- **Absent vs corrupt are different.** A *missing* `ditto.lock` is legitimate (fall back / bootstrap). A *present but unparseable* one fails loudly — silent fallback could mask drift.
- **`version: 1`.** An unknown future version refuses with an "upgrade ditto" message rather than misparsing.
- **Append never crashes a run.** A failed lock-file write warns and continues (same pattern as the existing prune-delete handling, `plugin.py:747`). In `verify`/CI mode, a *read* failure does fail — that is the guard's purpose.

---

## Concurrency

- **Atomic writes (integrity, not mutual exclusion):** write the full content to a temp file *in the same directory*, then `os.replace` it onto `ditto.lock`. A naïve `open("w")` truncates the file and writes incrementally, leaving a window in which the on-disk file is empty or half-written; this prevents a concurrent reader (`ditto list`/`verify`, a second `pytest`) from seeing a partial file and prevents an interrupted or crashed write from leaving a corrupt committed `ditto.lock` — the original stays intact until the swap. The same-directory detail is load-bearing: `os.replace` is only atomic within one filesystem, so a temp file on a different mount (e.g. `/tmp`) would silently degrade to a non-atomic copy. Done unconditionally because it is free; it guarantees the file is never *corrupt*, but does not prevent the lost-update race below.
- **xdist posture (matches the library, does not extend it):** detect an xdist worker (`workerinput` on `config`) and **skip all lock-file mutation** (append/update/prune/lock) in that process — lock-file mutation is a single-process concern, exactly as the session report and prune already are. Under `pytest -n auto` the parallel run does not mutate the committed lock file; maintain it with single-process `ditto lock` / `ditto update`.
- **`verify` is xdist-safe** because it is read-only: each worker asserts its own slice with no write and no corruption risk, so the CI guard still works under parallel CI.
- **Two independent appending processes:** last-writer-wins on a read-modify-write race could drop one freshly-created entry. Acceptable and self-healing — atomic replace prevents corruption, `verify` catches the gap, and a re-run or `ditto lock` fixes it. Cross-process file locking is YAGNI for a committed dev artifact.

---

## Migration / Adoption (non-breaking)

- Existing projects have snapshots but no lock file, and normal runs only append *created* keys (existing snapshots *load*, so the lock file would stay empty). **`ditto lock`** is the one-shot bootstrap: a full, non-destructive run that records the accessed-or-created set without altering any snapshot bytes.
- **No lock file present** → read commands fall back to current behavior; `--ditto-prune` falls back to today's access-based prune but **warns it is non-authoritative** and points to `ditto lock`. The whole feature is opt-in and breaks nothing.
- **Bootstrap checks `.gitignore`** and warns if `ditto.lock` matches an ignore pattern — it must be committed to do its job.

---

## Testing Strategy

**Unit (pure, no pytest spawn):**

- `_lockfile.py` round-trip: `to_json`/`from_json`, deterministic sorting, one-entry-per-line formatting, unknown-`version` refusal.
- Portable-id functions: canonical absolute `file://` URI ↔ rootdir-relative id; remote URIs pass through verbatim.
- Storage-key derivation from `(nodeid, key, recorder)` → `_flat_key` (file) and `str(SnapshotKey)` (remote), including dotted exts like `pandas.parquet`.
- Set algebra for the four flows (append-union, authoritative-rewrite, prune-orphan-diff within owned prefixes, verify-diff) as pure functions over in-memory sets.
- Owned-prefix scoping: a key outside the project's prefixes is never an orphan candidate (the shared-remote guarantee).

**Integration (`pytester`, in-process, `memory://`):**

- Append-only invariant: a `-k` partial run adds but never removes.
- `ditto update` removes a deleted test's entry on a full run; refuses on a filtered run.
- In-session `--ditto-prune` deletes a lock-absent orphan but leaves a deselected test's snapshot intact (#76 P1 guard).
- A failed test does not cause its snapshot to be pruned (#76 P2 guard).
- `verify` fails on missing-value, orphan, and unsynced-new-key; passes clean.
- `ditto lock` bootstrap builds a complete lock file from existing snapshots without altering their bytes.
- xdist posture: an xdist worker performs no lock-file write (assert file unchanged under `-n 2`); `verify` works read-only per worker.

**CLI:**

- `list`/`stats`/`status` render from the lock file with no pytest subprocess and no credentials (assert against a remote-scheme lock entry with no network).
- `--live` triggers the introspection pass and enriches sizes.
- Fallback when `ditto.lock` is absent (legacy behavior + adoption hint); loud failure when present but corrupt.

**Determinism / review-friendliness:**

- Golden-file test: a representative `ditto.lock` is byte-stable across runs, and an unrelated addition produces a minimal, line-disjoint diff.

---

## Problems Resolved

| Ref | Problem | Resolved by |
|---|---|---|
| #76 P1 | Partial selection within a run module over-deletes | Lock-file authority (prune flow) |
| #76 P2 | Failed test → valid snapshot pruned | Lock-file authority (prune flow) |
| #76 P3 | Shared/remote backend holds keys for other suites/branches | Owned-prefix scoping |
| #76 P4 | Unhashable `storage_options` reopens cross-deletion | Authority decoupled from backend identity/access |
| #76 P5 | Weak partial-run detection | Authority decoupled from run completeness |
| #76 P6 | Non-atomic, unreviewable destructive prune | Two-phase `ditto prune` |
| #77 | Heavyweight CLI introspection | Lock-file-first inventory; `--live` opt-in |
