# Baselines and the lock

Read this reference before changing snapshot ownership, deleting snapshots,
resetting baselines, or migrating from 1.x. Use the installed command help to
confirm available flags.

## Command effects

All pytest-running commands execute test bodies and fixtures, which can have
their own side effects. "Read-only" below refers to ditto's snapshots and lock.

| Command | Snapshots | `ditto.lock` |
| --- | --- | --- |
| `pytest` / `ditto run` | Records missing values; loads existing ones for test assertions. | Appends newly recorded entries in a single-process run. |
| `ditto update` | Overwrites every value the run reaches. | Rebuilds exercised targets on a full, passing run; otherwise only appends. |
| `ditto verify` | Reads existing values; never records missing ones. | Reads the lock; fails on missing, orphan, or unsynced snapshots. |
| `ditto lock` | Records missing values; leaves existing values unchanged. | Rebuilds from a full, passing run. |
| `ditto prune --check` | Runs tests, potentially recording missing values; previews deletions. | Reads the lock without writing it. |
| `ditto prune` | Runs tests, potentially recording missing values; deletes eligible orphans. | Reads the lock without writing it. |
| `ditto clean PATH` | Deletes local `.ditto/` directories under PATH. | Leaves the lock unchanged. |

A normal run can pass after recording a missing baseline. A verify run leaves
that baseline absent and fails on drift instead. Investigate a missing committed
baseline before accepting newly generated output as its replacement.

Verify compares storage membership with the lock, not payload hashes. The tests'
assertions compare values. It examines only targets the run exercises; selected
tests can still expose an orphan elsewhere in the same exercised target.

Verify, lock, and prune refuse pytest-xdist distribution. Use `-n 0` if the
project's configuration enables xdist. Distributed normal and update runs can
write snapshots but do not maintain the lock; finish ownership maintenance in
a single-process run.

## Add or update a baseline

For a new snapshot test, run the relevant tests normally and review the recorded
contents. For an intentional behavior change, update the affected tests:

```bash
ditto update tests/test_api.py::test_response
ditto verify tests/test_api.py::test_response
```

Run these commands through the project's existing runner. Quote node IDs that
contain shell metacharacters, such as parameter IDs in brackets. Every snapshot
call reached by the selected test is updated, including other keys in that test.

Review the actual values and any new files, plus the lock diff. Include local
snapshots and `ditto.lock` with the test changes in version control. A missing or
unwritable lock is not a reason to replace it by hand.

## Rename, remove, or change identity

A test rename, parametrize ID, key, or recorder change creates a different
snapshot identity and leaves the old one behind. Let ditto generate the names;
do not infer them from their readable labels or rename files to guess the hash.

When the task includes removing the obsolete baselines:

```bash
ditto lock
ditto prune --check
ditto prune
ditto verify
```

`ditto lock` must run the full configured suite, without positional paths or
node IDs or filters such as `-k`, `-m`, `--lf`, or `--ff`. It refuses narrowed or
failing rebuilds. Review the rebuilt lock and the deletion candidates before
pruning within the authorized scope.

A rebuild updates exercised targets, preserves targets not used by the run,
and preserves entries for tests that were skipped, xfailed, or excluded from
execution. Do not treat a machine-specific skip as proof that its snapshots are
obsolete.

Prune deletes keys absent from the lock under owned test-module prefixes. A
filtered run examines fewer targets, but can delete every eligible orphan in
each one it examines. Keys created during that run are kept and reported as
unsynced. `--check` suppresses deletion, not recording.

Read [backends](backends.md) before pruning a remote target or a local path
outside the project. `--shared` acknowledges potential shared storage; it does
not establish exclusive ownership.

## Retire a target or reset local storage

When no test uses a target any more, lock rebuilding preserves it, and verify
and prune do not examine it. If the task explicitly retires that target, inspect
its storage and ownership, remove only its snapshots, remove its block under
`targets` in the lock, then run lock and verify. This is the documented exception
to generating the lock rather than editing it by hand; it is not routine cleanup.

`ditto clean` resets all local `.ditto/` directories in its selected path. It
does not remove remote snapshots or the lock, and it skips symlinked `.ditto`
entries. Use it for an authorized local reset, not to fix an unexplained mismatch.
Without a terminal it refuses deletion unless `--yes` is supplied; use that flag
only when the deletion scope is already authorized.

## Upgrade from 1.x

2.x changes the default recorder to strict JSON and changes snapshot names.
It does not find or migrate 1.x baselines, including `.pkl` files. Preserve the
old baselines for review, record the intended new representations, inspect every
replacement against expected behavior, replay the tests, then rebuild ownership
and remove only the reviewed obsolete files. Recording new output does not prove
equivalence with the old baseline. The external pickle recorder uses `.pickle`.

Further details: [maintenance](https://owlowlyowl.github.io/pytest-ditto/guides/maintaining/)
and [upgrading](https://owlowlyowl.github.io/pytest-ditto/upgrading/).
