# Upgrading

## Upgrading to 2.0

pytest-ditto 2.0 changes the unmarked default from pickle to strict JSON and
removes pickle from the core distribution. Existing `.pkl` snapshots are
ignored by the JSON path: core does not inspect, load, compare, convert, or
migrate them.

When a `.json` snapshot is absent, a normal or update run follows ordinary
missing-snapshot behavior and records current test output as new JSON, even if
a same-key `.pkl` file exists. A read-only verification run reports the JSON key
as missing. Re-recording does not prove that the current output is equivalent
to the old baseline.

Use this upgrade workflow:

1. Upgrade and run the complete test suite to create missing JSON snapshots.
2. For strict-JSON failures, change the snapshotted representation or select a
   suitable installed recorder.
3. Review every new JSON snapshot. It was recorded from current output, not
   converted or compared with pickle.
4. Run the complete suite again.
5. Run `ditto lock` only after accepting the new baselines.
6. Delete the old `.pkl` files by hand, for example with
   `find . -path '*/.ditto/*.pkl' -delete`. `ditto prune` doesn't remove them:
   1.x names don't start with the test module, so prune never treats them as
   belonging to your suite.

If pickle is deliberately required, install `pytest-ditto-pickle` and select
its recorder explicitly. Loading pickle data can execute arbitrary code, so
only load trusted snapshots. Core provides no pickle warning, guard, migration
command, or convenience extra.

`pytest-ditto-pickle` names its snapshot files after the recorder, so they end
in `.pickle`, not `.pkl`. It doesn't find 1.x `.pkl` files either: 2.0 names
include the test module and a hash, so a 1.x snapshot can't be renamed into
place by hand. Re-record it with the pickle recorder and review the result as
in the workflow above. If you used
`pytest-ditto-pickle` 2.0.0b1, which still wrote `.pkl`, rename those snapshots
to end in `.pickle` and run `ditto lock`.

Version 2.0 registers the pytest plugin under the name `ditto` instead of
`recording`, which collided with the `pytest-recording` plugin. To disable
pytest-ditto for a run, use `-p no:ditto` in place of `-p no:recording`.

Version 2.0 also removes `DittoTestCase`. Unittest-style classes collected by
pytest should use pytest fixtures and marks. Direct `Snapshot` construction is
the lower-level alternative when fixture injection is unsuitable.

A directly constructed `Snapshot` takes a single `mode` in place of the
`update` and `readonly` flags: `Snapshot(..., mode=SnapshotMode.UPDATE)` replaces
`update=True`, and `mode=SnapshotMode.VERIFY` replaces `readonly=True`. The
default, `SnapshotMode.RECORD`, matches the old defaults. Import `SnapshotMode`
from `ditto`. A `Snapshot` given a `recorder` also needs `recorder_name=`, the
name the recorder is registered under, which names its snapshot files:
`Snapshot(..., recorder=recorders.get("yaml"), recorder_name="yaml")`. Passing
one without the other raises `TypeError`. Omit both for strict JSON.

Recorders serialise to bytes: a `Recorder` is `Recorder(dumps=..., loads=...)`,
where `dumps` turns a value into the snapshot file's bytes and `loads` turns
them back. The path-based `Recorder(save=..., load=...)` is gone. A plugin still
built on it fails to load with a message saying so. Rebuild it on the
library's in-memory functions, or wrap its file functions with
`ditto.recorders.recorder_from_files`. See
[Custom Recorders](custom-recorders.md).

`snapshot()` now returns the value as the recorder reads it back on every run.
Before, the run that recorded or updated a snapshot, or verified a missing one,
returned the value passed in. A value the recorder doesn't store exactly used
to pass on that run and fail on the next one; it now fails straight away. For
example, the YAML recorder reads a tuple back as a list, so
`assert (1, 2) == snapshot((1, 2), key="pair")` under `@ditto.yaml` now fails
when first recorded. Snapshot a list instead, or use a recorder that keeps the
distinction. A recorder whose `loads` can't read the bytes its `dumps` produced
now raises before anything is written.

Under pytest-xdist distribution (`-n N`, or `--dist` with `--tx`),
`--ditto-verify`, `--ditto-lock`, `--ditto-prune` and `--ditto-prune-dry-run`
are now a usage error (exit code 4), raised before any test runs. Before,
verify passed without checking anything, prune only warned, and `--ditto-lock`
failed only after the whole suite had run under `-n`. Run these single-process,
after a parallel test run if you like. See
[Running under pytest-xdist](lock-file.md#running-under-pytest-xdist).

YAML and `pytest-ditto-pandas` CSV snapshots are now written with `"\n"` line
endings on every platform, as JSON already was. On Windows, snapshots those
recorders wrote before used `"\r\n"`. They still load; the next
`--ditto-update` rewrites them with `"\n"`, a one-time line-ending diff.

Git on Windows often converts line endings on checkout (`core.autocrlf`), which
gives a working copy with `"\r\n"` while ditto writes `"\n"`. Snapshots still
load, but to keep them byte-for-byte what ditto wrote, add this to your
repository's `.gitattributes`:

```gitattributes
# Snapshots are byte-exact: never convert their line endings.
**/.ditto/** -text
```

If snapshots live in a directory other than `.ditto`, for example one set with
`ditto_target`, add a line for that directory too.

Version 2.0 refuses target URIs that contain a password or a secret query
parameter, such as `redis://alice:secret@host` or an Azure SAS URL's `sig=`,
because target URIs are recorded in `ditto.lock`. Move those credentials into
the `ditto_storage_options` fixture, or, for a target profile, into the
profile's `storage_options` (a profile ignores `ditto_storage_options`). See
[Credentials and connection settings](backends.md#credentials-and-connection-settings-ditto_storage_options).

`ditto prune` no longer deletes from a target that other checkouts might
share, such as a remote URI or a `file://` path outside the project (after
following symlinks), unless you pass `--shared` (`pytest --ditto-prune-shared`).
Another branch's snapshots on such a target look like orphans, so first make
sure each project and branch has its own target path. See
[Sharing a target](lock-file.md#sharing-a-target).

`ditto prune` (`--ditto-prune`) and `ditto prune --check`
(`--ditto-prune-dry-run`) now fail the run when they can't read a target, and
`ditto prune` fails when it can't delete a snapshot. Before, both only warned
and exited 0, so a CI prune step passed with the orphans still there.

## Snapshot Key Format Change

Recent versions changed how snapshot keys are derived. Snapshots recorded by
older versions will not be found after upgrading:

- **`file://` snapshots** are now stored as flat
  `module.test@key~hash.recorder` files (one `.ditto/` directory, no
  per-module subdirectories). Remote snapshots use the same name with the
  module path's slashes kept. The test and key are made safe for every file
  system and the hash keeps names apart; see
  [Storage Backends](backends.md#local-files-file).
- **Snapshots recorded by 2.0.0b1** used names without the hash
  (`module.test@key.recorder`), so they aren't found either. `ditto lint`
  reports them as malformed names.
- **Class-based test keys** now include the class name
  (`TestClass.test_method` rather than `test_method`)

## Migration Steps

Because a missing snapshot is **recorded and passes** rather than failing, an
upgrade will silently re-record every snapshot from your code's current output
on the next run.

To avoid masking a regression:

1. **Re-record deliberately** with `--ditto-update`:

    ```bash
    ditto update
    ```

2. **Review the regenerated snapshots** in your diff — do not trust the first
   green run after upgrading

3. **Commit** the updated snapshots once you're satisfied

## Migration from `ditto_backend`

If you previously used a `ditto_backend` fixture, migrate to the
`target=` + backend registration model:

1. Register a URI scheme under `ditto_backends`:

    ```toml
    [project.entry-points.ditto_backends]
    myscheme = "my_package:create_backend"
    ```

2. Move runtime auth and connection kwargs into `ditto_storage_options`:

    ```python
    @pytest.fixture(scope="session")
    def ditto_storage_options():
        return {"myscheme": {"password": os.environ["PASSWORD"]}}
    ```

3. Select the backend with `target=` or `ditto_target`:

    ```toml
    [tool.pytest.ini_options]
    ditto_target = "myscheme://host/db"
    ```
