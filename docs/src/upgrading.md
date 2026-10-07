# Upgrading to 2.0

pytest-ditto 2.0 stores snapshots under new names and in strict JSON by
default, so it finds none of the snapshots 1.x recorded. A plain run records
them all again from your code's current output, and passes. Follow the workflow
below so that first green run doesn't hide a regression.

## Upgrade workflow

1. **Upgrade** pytest-ditto, and any recorder plugins you use, to 2.0.
2. **Make the code changes** that apply to you from
   [What changed](#what-changed): marks and recorders, a `ditto_backend`
   fixture, `DittoTestCase`, credentials in target URIs.
3. **Run the complete suite** to record every snapshot under its new name:

    ```bash
    pytest
    ```

    Tests that snapshot values outside strict JSON fail. Change what they
    snapshot, or select a suitable [recorder](guides/recorders.md).

4. **Review every new snapshot** in your diff. Each was recorded from current
   output, not converted from or compared with the 1.x baseline.
5. **Run the complete suite again**, then record the lock:

    ```bash
    pytest
    ditto lock
    ```

6. **Delete the 1.x snapshot files.** `ditto lint` lists them as malformed
   names. Delete them by hand: `ditto prune` doesn't remove them, because their
   names don't start with the test module, so prune never treats them as
   belonging to your suite.
7. **Commit** the new snapshots, the deletions and `ditto.lock` together. Then
   set up CI to run `ditto verify`; see [Running in CI](guides/ci.md).

## What changed

### Strict JSON is the default; pickle is a plugin

The unmarked default changes from pickle to strict JSON, and pickle moves out
of the core distribution. Core ignores existing `.pkl` snapshots: it doesn't
inspect, load, compare, convert or migrate them. A read-only `ditto verify` run
reports their JSON replacements as missing until they're recorded.

If you need pickle, install `pytest-ditto-pickle` and select its recorder
explicitly with `@ditto.pickle`. Loading pickle data can execute arbitrary
code, so only load trusted snapshots. Core provides no pickle warning, guard,
migration command or convenience extra.

`pytest-ditto-pickle` names its snapshot files after the recorder, so they end
in `.pickle`, not `.pkl`. It doesn't find 1.x `.pkl` files either: re-record
them with the pickle recorder and review the result, as in the workflow above.

### Snapshot names

Snapshots are stored under new names, so none recorded by 1.x are found:

- A local snapshot is one file directly in `.ditto/`, named
  `module.test@key~hash.recorder`, with no per-module subdirectories. Remote
  snapshots use the same name with the module path's slashes kept.
- A test in a class includes the class name (`TestClass.test_method` rather
  than `test_method`).
- The name ends with the recorder's registered name, such as `.json`, `.yaml`
  or `.pandas.parquet`.

See [Snapshot Names](concepts/naming.md).

### `snapshot()` returns the value as read back

`snapshot()` now returns the value as the recorder reads it back on every run.
Before, the run that recorded or updated a snapshot, or verified a missing one,
returned the value passed in. A value the recorder doesn't store exactly used
to pass on that run and fail on the next one; it now fails straight away. For
example, the YAML recorder reads a tuple back as a list, so
`assert (1, 2) == snapshot((1, 2), key="pair")` under `@ditto.yaml` now fails
when first recorded. Snapshot a list instead, or use a recorder that keeps the
distinction. A recorder whose `loads` can't read the bytes its `dumps` produced
now raises before anything is written.

### The pytest plugin is named `ditto`

Version 2.0 registers the pytest plugin under the name `ditto` instead of
`recording`, which collided with the `pytest-recording` plugin. To disable
pytest-ditto for a run, use `-p no:ditto` in place of `-p no:recording`.

### `DittoTestCase` is removed

Unittest-style classes collected by pytest should use pytest fixtures and
marks. Direct `Snapshot` construction is the lower-level alternative when
fixture injection is unsuitable.

A directly constructed `Snapshot` takes a single `mode` in place of the
`update` and `readonly` flags: `Snapshot(..., mode=SnapshotMode.UPDATE)`
replaces `update=True`, and `mode=SnapshotMode.VERIFY` replaces
`readonly=True`. The default, `SnapshotMode.RECORD`, matches the old defaults.
Import `SnapshotMode` from `ditto`. A `Snapshot` given a `recorder` also needs
`recorder_name=`, the name the recorder is registered under, which names its
snapshot files: `Snapshot(..., recorder=recorders.get("yaml"),
recorder_name="yaml")`. Passing one without the other raises `TypeError`. Omit
both for strict JSON.

### Recorders serialise to bytes

A `Recorder` is `Recorder(dumps=..., loads=...)`, where `dumps` turns a value
into the snapshot file's bytes and `loads` turns them back. The path-based
`Recorder(save=..., load=...)` is gone. A plugin still built on it fails to
load with a message saying so. Rebuild it on the library's in-memory functions,
or wrap its file functions with `ditto.recorders.recorder_from_files`. See
[Writing a Recorder](guides/custom-recorders.md).

### The `ditto_backend` fixture is replaced by registered backends

A `ditto_backend` fixture now raises an error. Register a URI scheme for your
backend and select it with a target instead:

1. Register a URI scheme under `ditto_backends`:

    ```toml
    [project.entry-points.ditto_backends]
    myscheme = "my_package:create_backend"
    ```

2. Move runtime auth and connection keyword arguments into
   `ditto_storage_options`:

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

See [Writing a Backend](guides/custom-backends.md).

### Credentials can't go in target URIs

Version 2.0 refuses target URIs that contain a password or a secret query
parameter, such as `redis://alice:secret@host` or an Azure SAS URL's `sig=`,
because target URIs are recorded in `ditto.lock`. Move those credentials into
the `ditto_storage_options` fixture, or, for a target profile, into the
profile's `storage_options` (a profile ignores `ditto_storage_options`). See
[Credentials and connection settings](guides/backends.md#credentials-and-connection-settings-ditto_storage_options).

### Verify, lock and prune refuse pytest-xdist

Under pytest-xdist distribution (`-n N`, or `--dist` with `--tx`),
`--ditto-verify`, `--ditto-lock`, `--ditto-prune` and `--ditto-prune-dry-run`
are now a usage error (exit code 4), raised before any test runs. Before,
verify passed without checking anything, prune only warned, and `--ditto-lock`
failed only after the whole suite had run under `-n`. Run these single-process,
after a parallel test run if you like. See
[Running tests in parallel](guides/ci.md#running-tests-in-parallel).

### Prune leaves shared targets alone, and fails when it can't finish

`ditto prune` no longer deletes from a target that other checkouts might
share, such as a remote URI or a `file://` path outside the project (after
following symlinks), unless you pass `--shared` (`pytest --ditto-prune-shared`).
Another branch's snapshots on such a target look like orphans, so first make
sure each project and branch has its own target path. See
[Sharing a target](concepts/lock-file.md#sharing-a-target).

`ditto prune` (`--ditto-prune`) and `ditto prune --check`
(`--ditto-prune-dry-run`) now fail the run when they can't read a target, and
`ditto prune` fails when it can't delete a snapshot. Before, both only warned
and exited 0, so a CI prune step passed with the orphans still there.

### Line endings are `"\n"` everywhere

YAML and `pytest-ditto-pandas` CSV snapshots are now written with `"\n"` line
endings on every platform, as JSON already was. On Windows, snapshots those
recorders wrote before used `"\r\n"`. They still load; the next
`--ditto-update` rewrites them with `"\n"`, a one-time line-ending diff. To stop
Git converting them on checkout, see
[Commit your snapshots and the lock](guides/ci.md#commit-your-snapshots-and-the-lock).

## Upgrading from a 2.0 pre-release

- **2.0.0b1** named snapshots without the hash (`module.test@key.recorder`), so
  they aren't found. `ditto lint` reports them as malformed names. Re-record
  them as in the [upgrade workflow](#upgrade-workflow) and delete the old files.
- **`pytest-ditto-pickle` 2.0.0b1** wrote `.pkl` files, also without the hash.
  Re-record them with the current plugin, which writes `.pickle`, in the same
  way.
