# Running in CI

A snapshot test only protects you if CI fails when a snapshot is missing or
wrong. This guide covers what to commit, which command CI should run, and how
to run in parallel and against remote storage.

## Commit your snapshots and the lock

Commit everything your tests read back:

- the snapshot directories, such as each `.ditto/` directory next to your tests
- `ditto.lock`, in pytest's rootdir, which records every snapshot your suite
  owns (see [The Lock File](../concepts/lock-file.md))

Review both in pull requests like any other change: a changed snapshot is a
changed expected output.

Snapshots are byte-exact. Git on Windows often converts line endings on
checkout (`core.autocrlf`), which gives a working copy with `"\r\n"` while
ditto writes `"\n"`. Snapshots still load, but to keep them byte-for-byte what
ditto wrote, add this to your repository's `.gitattributes`:

```gitattributes
# Snapshots are byte-exact: never convert their line endings.
**/.ditto/** -text
```

If snapshots live in a directory other than `.ditto`, for example one set with
`ditto_target`, add a line for that directory too.

## Run `ditto verify`, not plain `pytest`

A plain `pytest` run records any snapshot that is missing and passes. In CI
that hides a problem: a snapshot that was never committed, or that a rename
orphaned, is silently recreated from the code's current output.

Run [`ditto verify`](../cli/verify.md) instead. It runs your whole suite, so
every test's assertions still compare against the stored snapshots, but it
never writes. On top of the tests' own results, it fails when storage and
`ditto.lock` disagree:

- a snapshot the lock records is missing from storage
- storage holds a snapshot the lock doesn't record (an orphan)
- a test produced a snapshot the lock doesn't record yet

```bash
ditto verify
```

`ditto verify` takes pytest's arguments, so options you pass to `pytest` in CI
work here too. It needs a `ditto.lock`: without one it fails and tells you to
run `ditto lock`.

## Running tests in parallel

Snapshot tests run under pytest-xdist distribution (`-n N`, or `--dist` with
`--tx`): each worker records and compares its own tests' snapshots. What doesn't
work is anything that has to see the whole run in one process, because the tests
run in the workers and no single process sees them all:

| Under distribution | Behaviour |
|---|---|
| `pytest` / `ditto update` | Snapshots are recorded and compared as usual. `ditto.lock` is not updated; ditto warns. |
| `ditto verify` (`--ditto-verify`) | Refused. |
| `ditto lock` (`--ditto-lock`) | Refused. |
| `ditto prune` (`--ditto-prune`, `--ditto-prune-dry-run`) | Refused. |
| Snapshot report | Not printed. |

A refused mode is a usage error (exit code 4) raised before any test runs, so it
writes no snapshots, leaves the lock as it was, and deletes nothing.

To run the tests in parallel, run them first, then check the lock in a
separate single-process run:

```bash
pytest -n auto
ditto verify -n 0
```

`ditto verify` runs the suite again. The `-n 0` turns distribution off when
your pytest configuration adds `-n` through `addopts`; without such an
`addopts`, it does nothing.

## Remote storage in CI

Pass credentials through the `ditto_storage_options` fixture, reading them
from the environment your CI provides; ditto refuses a target URI that contains
a password. See
[Credentials and connection settings](backends.md#credentials-and-connection-settings-ditto_storage_options).

Give each project, and each branch whose tests can differ, its own remote path.
Otherwise one branch's snapshots look like orphans to another, so `ditto
verify` reports them and `ditto prune` would delete them. Set the path on the
command line with the branch name filled in:

```bash
ditto verify -o "ditto_target=s3://my-bucket/my-project/$BRANCH/"
```

See [Sharing a target](../concepts/lock-file.md#sharing-a-target).

## Don't update snapshots in CI

`ditto update` overwrites snapshots with whatever the code produces now, so
running it in CI would accept any change. Update snapshots locally, review the
diff, and commit them; see [Maintaining Snapshots](maintaining.md).

To report orphans in CI without deleting anything, run `ditto prune --check`.
Like `ditto prune`, it fails when it can't read a target.
