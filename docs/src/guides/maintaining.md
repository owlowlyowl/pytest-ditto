# Maintaining Snapshots

Snapshots change as your code does. This guide covers the everyday tasks:
adding snapshots, accepting an intended change, cleaning up after renamed or
removed tests, and inspecting what's stored. Each task ends the same way:
review the changed snapshots and `ditto.lock` in your diff, and commit them
together.

## Add a snapshot

Write the test and run it:

```bash
pytest tests/test_api.py
```

The first run stores the snapshot and adds its entry to `ditto.lock`. Check the
new snapshot file holds what you expect before committing it: from now on, the
test compares against it.

## Accept an intended change

When your code's output changes on purpose, the tests that snapshot it fail.
Re-record their snapshots from the current output:

```bash
ditto update                              # every snapshot
ditto update tests/test_api.py            # one file
ditto update tests/ -k test_create_user   # matching tests
```

`ditto update` overwrites each snapshot the run reaches. Review the diff
carefully: it accepts whatever the code produces now, including a regression.

A full, passing `ditto update` also rebuilds `ditto.lock`, as `ditto lock`
does. A filtered or failing one only adds entries; if you renamed anything, run
`ditto lock` afterwards (below).

## Remove snapshots you no longer need

Renaming or deleting a test, changing a parametrize ID, a key or a recorder all
leave the old snapshot behind, because its name no longer matches anything. To
clean up:

```bash
ditto lock           # drop entries for snapshots no test produces any more
ditto prune --check  # list what would be deleted
ditto prune          # delete every stored snapshot the lock doesn't record
```

`ditto lock` runs the whole suite and must pass; it refuses a filtered run. See
[ditto lock](../cli/lock.md) and [ditto prune](../cli/prune.md), including why
prune leaves a remote target alone unless you pass `--shared`.

## Retire a target

`ditto lock` keeps the entries of every target the run doesn't use, so a suite
that reaches some backends only on some machines doesn't lose them. The
flip side is that when you delete the last test using a target, or move all
its tests to another target, nothing cleans the old one up: `ditto lock`
keeps its entries, and `ditto prune` and `ditto verify` don't look at it.

To retire a target:

1. Delete its snapshots from storage, for example by deleting its directory or
   its prefix in the bucket.
2. Remove the target's block from `ditto.lock`, under `"targets"`. A target
   inside the project is keyed by its path relative to the rootdir, such as
   `"tests/legacy/.ditto"`; any other target by its URI.
3. Run `ditto lock` and `ditto verify` to check the result, and commit the lock.

This is the one case where you edit `ditto.lock` by hand.
[Issue #249](https://github.com/owlowlyowl/pytest-ditto/issues/249) tracks a
supported way to do it.

## Inspect what's stored

These commands read your snapshots without running the tests:

| Command | Shows |
|---|---|
| [`ditto list`](../cli/list.md) | every snapshot, with its test, key, recorder, size and date |
| [`ditto status`](../cli/status.md) | totals, broken down by recorder |
| [`ditto stats`](../cli/stats.md) | count and size per target |
| [`ditto lint`](../cli/lint.md) | malformed names, unknown recorders and empty files |

Local snapshots are read from disk; remote ones from `ditto.lock`, without
credentials. Pass `--live` to read remote storage itself.

To check that storage and the lock agree, run [`ditto verify`](../cli/verify.md).

## Check your installation

[`ditto doctor`](../cli/doctor.md) checks that the pytest plugin and every
installed recorder and backend plugin load, and that their registrations are
valid. [`ditto recorders`](../cli/recorders.md) lists the installed recorders
and their marks.

## Start over locally

[`ditto clean`](../cli/clean.md) deletes every `.ditto/` directory under a
path. It doesn't touch `ditto.lock` or remote storage, so afterwards run the
tests to record the snapshots again, and `ditto verify` to confirm the lock
still matches.
