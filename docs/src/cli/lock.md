# ditto lock

Rebuilds `ditto.lock` from the snapshots your suite currently holds. Run it
after adding, renaming or removing a snapshot, and after changing a test's node
ID, so the lock records the identities your suite actually produces.

See [The Lock File](../concepts/lock-file.md) for the model behind the file.

## Usage

```
ditto lock [PYTEST_ARGS]
```

`ditto lock` re-runs your suite with `--ditto-lock`; extra arguments are passed
through to pytest.

By default the suite runs in RECORD mode: snapshot calls reuse existing values
and **create missing snapshots**. Existing values are not overwritten. Your
test assertions compare those values with current expectations, and an assertion
failure prevents the lock rebuild. Use [`ditto update`](update.md) to overwrite
existing values; passing `--ditto-update` to this command also selects UPDATE mode.

After a successful full run, the command rebuilds the lock's snapshot identities.
It does not check backend drift: an orphan can remain without failing this run.
Use [`ditto verify`](verify.md) for a read-only check of missing, orphan and
unrecorded snapshots. The lock records identities, not expected snapshot values.

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

The lock is left unchanged when a rebuild is refused. Snapshots created during
test execution remain; refusal does not undo those writes. The reason is printed
rather than warned, so a warning filter cannot hide why the run failed:

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
or a skipping collector above it applied. For tests still present, a passing run
replaces their entries with the snapshots they actually accessed.

A target the run did not exercise is left as it was, so a suite that only
reaches some of its backends does not lose the others. To remove a target no test
uses any more, see
[Retire a target](../guides/maintaining.md#retire-a-target). An existing lock file
that cannot be parsed is replaced rather than being treated as fatal: a rebuild
is authoritative, and the entries for unexercised targets in a corrupt file are
unrecoverable either way.

The lock is a committed file. Commit it alongside the snapshot changes that
prompted the rebuild, so a reviewer sees which snapshots a change added.

## When the run fails

A test or collection failure prevents the rebuild and fails the run. A lock
that cannot be written also fails the run and prints the error. Backend drift
is checked separately by [`ditto verify`](verify.md).

## After a prune

Prune deletes orphans already absent from the lock, so deleting them does not
itself require a lock rebuild. When removing or renaming tests or snapshot keys,
first run `ditto lock` to drop obsolete identities from exercised targets, then
run `ditto prune` to remove the newly orphaned files.

A prune run can also create new snapshots while running tests. These remain
unsynced because prune does not append them to the lock. If prune warns about
snapshots produced during that run, use `ditto lock` to record their identities.
