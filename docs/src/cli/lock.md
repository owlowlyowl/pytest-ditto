# ditto lock

Rebuilds `ditto.lock` from the snapshots your suite currently holds. Run it
after adding, renaming or removing a snapshot, and after changing a test's node
ID, so the lock records the identities your suite actually produces.

See [The Lock File](../guides/lock-file.md) for the model behind the file.

## Usage

```
ditto lock [PYTEST_ARGS]
```

`ditto lock` re-runs your suite with `--ditto-lock`; extra arguments are passed
through to pytest.

The run reads every snapshot and compares it to the lock, but **never rewrites a
snapshot** — this is not `ditto update`. A value that has changed is reported as
drift, not silently re-recorded. Use [`ditto update`](update.md) to change a
value.

## Examples

```bash
# Rebuild the lock
ditto lock
```

## A full, clean run only

`ditto lock` must collect the **whole** suite, and it must pass. A narrowed or
failing run cannot rebuild the lock, because it cannot see the entries
belonging to tests it did not collect — writing it anyway would silently drop
them. So the run is refused when it used any of:

- a filter: `-k`, `-m`, `--lf`, `--ff`
- positional narrowing: a path or a `::nodeid` argument
- a failure, or any other non-zero exit status — a collection error counts,
  since a module that fails to import leaves no failed tests yet exits non-zero

Nothing is written when it is refused, and the reason is printed rather than
warned, so a warning filter cannot hide why the run failed:

```
ditto: --ditto-lock requires a full run (no -k/-m/--lf, no path/nodeid args, and no failures); leaving ditto.lock unchanged.
```

To run a subset, set the scope in configuration rather than on the command line:

```toml
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests/ci"]
```

## What it changes

`ditto.lock` is rewritten with the entries the run observed: one per snapshot,
per target, with the test's node ID, the key, and the recorder. Entries for tests
that no longer exist are dropped from the targets the run exercised, and new
ones are added.

A test that was collected but didn't pass — skipped, xfailed, deselected — keeps
the entries it had, as does a test pytest did not collect because an ignore path
or a skipping collector above it applied. Entries are only dropped for a test
that ran and no longer produced them.

A target the run did not exercise is left as it was, so a suite that only
reaches some of its backends does not lose the others. An existing lock file
that cannot be parsed is replaced rather than being treated as fatal: a rebuild
is authoritative, and the entries for unexercised targets in a corrupt file are
unrecoverable either way.

The lock is a committed file. Commit it alongside the snapshot changes that
prompted the rebuild, so a reviewer sees which snapshots a change added.

## When the run fails

A drift check that fails, or a lock that can't be written, fails the run — this
is lock maintenance you asked for, not bookkeeping to warn about. See
[`ditto verify`](verify.md) for what each kind of drift means; fix the snapshots
or the lock, then rebuild.

## After a prune

A prune deletes the snapshots the lock does not record, so the lock no longer
matches what a normal run reads. Rebuild it afterwards with `ditto lock`.
